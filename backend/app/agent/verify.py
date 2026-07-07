"""Verify phase — deterministic checks (pure) + the LLM verification panel.

Deterministic checks run at every depth and cost nothing. The LLM lenses are
named experts with distinct perspectives: the Domain Fidelity Guardian hunts
meaning drift / hallucination, the Evidence & Compliance Officer re-checks
regulatory substantiation, one revision loop fixes what they caught (full
depth), and the LLM Retrieval Expert judges before/after citation-readiness.
"""
from __future__ import annotations

import asyncio
import re

from app.agent.prompts import CITATION_JUDGE, COMPLIANCE_VERIFIER, REVISER, SKEPTIC
from app.agent.schemas import (
    BlockVerdict,
    CitationJudgement,
    RewriteBatch,
    VerificationBatch,
    VerificationReport,
)
from app.analysis.schemas import (
    PageSignals,
    Recommendation,
    RewriteBlock,
    SignalStatus,
    VerificationIssue,
    VerificationOutcome,
)

# Absolute/comparative promo phrases that regulated copy must not introduce.
FORBIDDEN_PHRASES = (
    "best",
    "cure",
    "cures",
    "guaranteed",
    "#1",
    "number one",
    "superior to",
    "safest",
    "proven to",
    "miracle",
    "breakthrough",
    "risk-free",
)

_NUM_RE = re.compile(r"\d[\d.,]*%?")

# Issue kinds that block a change from shipping (needs_human). Advisory kinds
# (missing_rationale, dropped flag quotes, page-level coverage notes) are
# recorded on the block but do not override an otherwise-sound rewrite.
BLOCKING_KINDS = {
    "unsupported_claim",
    "compliance",
    "meaning_drift",
    "broken_promise",
    "new_number",
    "compliance_lexicon",
}


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def _changed(blocks: list[RewriteBlock]) -> list[RewriteBlock]:
    return [b for b in blocks if b.changed]


# ------------------------------------------------------------ deterministic checks
def check_block_coverage(
    text_blocks, content_blocks: list[RewriteBlock]
) -> list[VerificationIssue]:
    """Every page block anchored exactly once (holds by construction; belt-and-braces)."""
    anchors = [b.anchor_id for b in content_blocks if b.anchor_id]
    issues = []
    for tb in text_blocks:
        n = anchors.count(tb.id)
        if n != 1:
            issues.append(
                VerificationIssue(
                    kind="block_coverage",
                    detail=f"Page block {tb.id} is anchored {n} times (expected exactly 1).",
                )
            )
    return issues


def check_rec_coverage(
    recs: list[Recommendation], blocks: list[RewriteBlock]
) -> list[VerificationIssue]:
    """Every P0/P1 recommendation with a concrete change must be implemented by
    some changed block (by rationale.recommendation_ids)."""
    implemented: set[str] = set()
    for b in _changed(blocks):
        if b.rationale:
            implemented.update(b.rationale.recommendation_ids)
    issues = []
    for rec in recs:
        if rec.priority.value in ("P0", "P1") and rec.change and rec.id not in implemented:
            issues.append(
                VerificationIssue(
                    kind="rec_unimplemented",
                    detail=f"{rec.id} ({rec.priority.value}) “{rec.title}” is not "
                    "implemented by any changed block.",
                )
            )
    return issues


def check_flag_quotes(blocks: list[RewriteBlock]) -> tuple[list[VerificationIssue], int]:
    """Every inline flag quote must appear verbatim in its block's proposed text.
    Violators are DROPPED (they cannot highlight); returns (issues, dropped_count)."""
    issues: list[VerificationIssue] = []
    dropped = 0
    for b in blocks:
        kept = [f for f in b.flags if f.quote and f.quote in b.proposed]
        n = len(b.flags) - len(kept)
        if n:
            dropped += n
            issues.append(
                VerificationIssue(
                    kind="flag_quote",
                    detail=f"{n} evidence flag(s) on {b.id} did not quote the proposed text verbatim and were dropped.",
                    block_id=b.id,
                )
            )
            b.flags = kept
    return issues, dropped


def check_no_new_numbers(page: PageSignals, blocks: list[RewriteBlock]) -> list[VerificationIssue]:
    """Numbers/percentages/dates in proposed text must already exist on the page —
    a cheap, strong anti-hallucination guard."""
    corpus = (page.main_text or "") + " " + " ".join(tb.text for tb in page.text_blocks)
    corpus_nums = set(_NUM_RE.findall(corpus))
    issues = []
    for b in _changed(blocks):
        if b.is_technical:
            continue  # code blocks legitimately contain new tokens (schema syntax)
        for num in set(_NUM_RE.findall(b.proposed)) - set(_NUM_RE.findall(b.original)):
            if num not in corpus_nums:
                issues.append(
                    VerificationIssue(
                        kind="new_number",
                        detail=f"Proposed text introduces “{num}” which appears nowhere on the page.",
                        quote=num,
                        block_id=b.id,
                    )
                )
    return issues


def check_forbidden_phrases(blocks: list[RewriteBlock]) -> list[VerificationIssue]:
    """Word-boundary lexicon scan on changed blocks — compliance floor."""
    issues = []
    for b in _changed(blocks):
        if b.is_technical:
            continue
        low = b.proposed.lower()
        for phrase in FORBIDDEN_PHRASES:
            for m in re.finditer(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", low):
                # only flag if the ORIGINAL didn't already contain it (we made it worse)
                if not re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", b.original.lower()):
                    issues.append(
                        VerificationIssue(
                            kind="compliance_lexicon",
                            detail=f"Proposed text introduces the promotional phrase “{phrase}”.",
                            quote=b.proposed[m.start() : m.start() + len(phrase)],
                            block_id=b.id,
                        )
                    )
                break  # one issue per phrase per block
    return issues


def check_rationales(blocks: list[RewriteBlock]) -> list[VerificationIssue]:
    """Every changed block must carry a usable explanation."""
    issues = []
    for b in _changed(blocks):
        rat = b.rationale
        if not b.change_explanation and not (rat and rat.why):
            issues.append(
                VerificationIssue(
                    kind="missing_rationale",
                    detail=f"Changed block {b.id} has no change_explanation and no rationale.why.",
                    block_id=b.id,
                )
            )
        elif rat and not rat.kb_factor_ids and not b.is_technical:
            issues.append(
                VerificationIssue(
                    kind="missing_rationale",
                    detail=f"Changed block {b.id} cites no KB factor in its rationale.",
                    block_id=b.id,
                )
            )
    return issues


def inherit_factor_ids(blocks: list[RewriteBlock], recs: list[Recommendation]) -> int:
    """Backfill a changed block's rationale.kb_factor_ids from the recommendations it
    implements (models often fill recommendation_ids but skip the factor ids).
    Returns how many blocks were patched."""
    rec_factors = {
        rec.id: rec.rationale.kb_factor_ids for rec in recs if rec.rationale
    }
    patched = 0
    for b in _changed(blocks):
        if not b.rationale or b.rationale.kb_factor_ids:
            continue
        inherited: list[str] = []
        for rid in b.rationale.recommendation_ids:
            for fid in rec_factors.get(rid.strip().lstrip("#"), []):
                if fid not in inherited:
                    inherited.append(fid)
        if inherited:
            b.rationale.kb_factor_ids = inherited
            patched += 1
    return patched


def ensure_explanations(blocks: list[RewriteBlock]) -> int:
    """Backfill change_explanation from rationale.why (and vice versa) where trivially
    fixable. Returns how many blocks were patched."""
    patched = 0
    for b in _changed(blocks):
        why = b.rationale.why if b.rationale else ""
        if not b.change_explanation and why:
            b.change_explanation = why
            patched += 1
        elif b.change_explanation and b.rationale and not b.rationale.why:
            b.rationale.why = b.change_explanation
            patched += 1
    return patched


def run_deterministic_checks(
    page: PageSignals, recs: list[Recommendation],
    content_blocks: list[RewriteBlock], technical_blocks: list[RewriteBlock],
) -> list[VerificationIssue]:
    """All pure checks in one pass (mutates: drops invalid flags, backfills explanations)."""
    blocks = [*content_blocks, *technical_blocks]
    ensure_explanations(blocks)
    inherit_factor_ids(blocks, recs)
    issues: list[VerificationIssue] = []
    issues += check_block_coverage(page.text_blocks, content_blocks)
    issues += check_rec_coverage(recs, blocks)
    flag_issues, _ = check_flag_quotes(blocks)
    issues += flag_issues
    issues += check_no_new_numbers(page, blocks)
    issues += check_forbidden_phrases(blocks)
    issues += check_rationales(blocks)
    return issues


# ------------------------------------------------------------ LLM lenses (panel)
def _blocks_for_review(blocks: list[RewriteBlock], max_chars: int = 20_000) -> str:
    """Compact original-vs-proposed listing of changed content blocks for a lens call."""
    lines: list[str] = []
    used = 0
    for b in blocks:
        entry = (
            f"### {b.id} ({b.label})\nORIGINAL: {b.original or '(net-new)'}\n"
            f"PROPOSED: {b.proposed}\n"
            f"RATIONALE: {(b.rationale.why if b.rationale else b.change_explanation) or '(none)'}\n"
        )
        if used + len(entry) > max_chars:
            break
        lines.append(entry)
        used += len(entry)
    return "\n".join(lines) or "(no changed blocks)"


def sanitize_verdicts(
    verdicts: list[BlockVerdict], blocks: list[RewriteBlock]
) -> list[BlockVerdict]:
    """Pure. Keep verdicts for known changed blocks only; discard issues whose
    `quote` is not verbatim in the proposed text (same discipline as flags)."""
    by_id = {b.id: b for b in blocks if b.changed}
    out: list[BlockVerdict] = []
    seen: set[str] = set()
    for v in verdicts:
        blk = by_id.get(v.block_id)
        if blk is None or v.block_id in seen:
            continue
        seen.add(v.block_id)
        kept = [i for i in v.issues if not i.quote or i.quote in blk.proposed]
        for i in kept:
            i.block_id = v.block_id
        if v.verdict not in ("pass", "revise", "fail"):
            v.verdict = "pass" if not kept else "revise"
        v.issues = kept
        # A non-pass verdict with no surviving issues has no evidence — downgrade.
        if v.verdict != "pass" and not kept:
            v.verdict = "pass"
        out.append(v)
    return out


async def run_llm_panel(ctx, emit, blocks: list[RewriteBlock], claims) -> list[BlockVerdict]:
    """Skeptic (Domain Fidelity Guardian) + Compliance Officer (full depth) over
    the changed blocks. Returns sanitized verdicts; failures degrade to no verdicts."""
    from app.agent.engine import BudgetExceeded

    changed = [b for b in blocks if b.changed and not b.is_technical]
    if not changed:
        return []
    claim_lines = "\n".join(
        f"- [{c.flag.value}] \"{c.text}\"" for c in claims if c.flag.value in ("red", "yellow")
    ) or "(none)"
    listing = _blocks_for_review(changed)
    user = (
        f"## Changed blocks (original vs proposed)\n{listing}\n\n"
        f"## Claim risks identified on the original page\n{claim_lines}"
    )
    lenses: list[tuple[str, str, str]] = [("verify.skeptic-1", "fidelity", SKEPTIC)]
    if ctx.depth.skeptic_mode == "batched":
        lenses.append(("verify.compliance", "compliance", COMPLIANCE_VERIFIER))

    async def one(step_id: str, agent: str, system: str) -> list[BlockVerdict]:
        title = (
            "Domain Fidelity Guardian: hunting meaning drift & unsupported claims"
            if agent == "fidelity"
            else "Evidence & Compliance Officer: re-checking proposed copy"
        )
        ctx.step_started(emit, "verify", step_id, title, agent=agent,
                         meta={"counts": {"blocks reviewed": len(changed)}})
        try:
            batch = await ctx.llm(
                system=system, user=user, schema=VerificationBatch,
                max_tokens=4000, temperature=0.0,
            )
            verdicts = sanitize_verdicts(batch.verdicts, changed)
            flagged = [v for v in verdicts if v.verdict != "pass"]
            ctx.step_completed(
                emit, "verify", step_id,
                meta={"agent": agent,
                      "counts": {"flagged": len(flagged)},
                      "findings": [f"{v.block_id}: {v.issues[0].detail[:80]}" for v in flagged[:5] if v.issues]},
            )
            return verdicts
        except BudgetExceeded:
            ctx.step_skipped(emit, "verify", step_id, title,
                             detail="Skipped — LLM call budget reached.", meta={"agent": agent})
            return []
        except Exception as exc:
            ctx.step_failed(emit, "verify", step_id, detail=str(exc), meta={"agent": agent})
            return []

    results = await asyncio.gather(*(one(s, a, p) for s, a, p in lenses))
    return [v for group in results for v in group]


async def run_revision(
    ctx, emit, blocks: list[RewriteBlock],
    to_fix: dict[str, list[VerificationIssue]],
    suggested: dict[str, str],
) -> set[str]:
    """One revision loop (full depth): rewrite the blocks that failed review.
    Returns the block ids that were actually revised."""
    from app.agent.engine import BudgetExceeded

    by_id = {b.id: b for b in blocks}
    targets = [by_id[bid] for bid in to_fix if bid in by_id and not by_id[bid].is_technical]
    if not targets:
        return set()
    lines = []
    for b in targets:
        issue_lines = "\n".join(f"  - [{i.kind}] {i.detail}" for i in to_fix[b.id])
        fix = suggested.get(b.id)
        lines.append(
            f"### {b.id} (anchor_id: {b.anchor_id or 'null'})\nORIGINAL: {b.original}\n"
            f"PROPOSED (failed review): {b.proposed}\nISSUES:\n{issue_lines}"
            + (f"\nSUGGESTED FIX: {fix}" if fix else "")
        )
    ctx.step_started(emit, "verify", "verify.revision",
                     f"Revising {len(targets)} blocks that failed review", agent="strategist",
                     meta={"block_ids": [b.id for b in targets]})
    try:
        batch = await ctx.llm(
            system=REVISER,
            user="## Blocks to revise\n" + "\n\n".join(lines),
            schema=RewriteBatch,
            max_tokens=8000,
            temperature=0.2,
        )
    except BudgetExceeded:
        ctx.step_skipped(emit, "verify", "verify.revision", "Revision loop",
                         detail="Skipped — LLM call budget reached.", meta={"agent": "strategist"})
        return set()
    except Exception as exc:
        ctx.step_failed(emit, "verify", "verify.revision", detail=str(exc),
                        meta={"agent": "strategist"})
        return set()

    revised: set[str] = set()
    returned = {rb.anchor_id: rb for rb in batch.blocks if rb.anchor_id}
    for b in targets:
        rb = returned.get(b.anchor_id or "")
        if rb is None or not (rb.proposed or "").strip():
            continue
        b.proposed = rb.proposed
        b.options = [rb.proposed]
        b.selected_option_index = 0
        if rb.flags:
            b.flags = [f for f in rb.flags if f.quote and f.quote in rb.proposed]
        if rb.change_explanation:
            b.change_explanation = rb.change_explanation
        if rb.rationale and rb.rationale.why:
            b.rationale = rb.rationale
        b.changed = _norm(b.proposed) != _norm(b.original)
        revised.add(b.id)
    ctx.step_completed(emit, "verify", "verify.revision",
                       meta={"agent": "strategist", "counts": {"revised": len(revised)}})
    return revised


async def run_citation_judge(
    ctx, emit, blocks: list[RewriteBlock]
) -> CitationJudgement | None:
    """LLM Retrieval Expert: before/after citation-readiness per engine (PREDICTED)."""
    from app.agent.engine import BudgetExceeded

    engines = ", ".join(e.value for e in ctx.request.target_engines)
    queries = "\n".join(f"- {q}" for q in ctx.result.queries) or "(none provided)"
    before_parts = [f"TITLE: {ctx.page.title or '(none)'}"]
    before_parts += [f"{tb.id}: {tb.text}" for tb in ctx.page.text_blocks[:15]]
    changed = [b for b in blocks if b.changed and not b.is_technical]
    after_parts = [f"{b.id} ({b.anchor_id or 'net-new'}): {b.proposed}" for b in changed[:25]]
    technical = [b for b in blocks if b.is_technical]
    tech_summary = "\n".join(f"- {b.label}" for b in technical) or "(none)"
    user = (
        f"## Engines to judge\n{engines}\n\n## User queries\n{queries}\n\n"
        f"## BEFORE — original key content\n" + "\n".join(before_parts) + "\n\n"
        f"## AFTER — changed blocks (proposed text)\n" + "\n".join(after_parts) + "\n\n"
        f"## AFTER — technical changes applied\n{tech_summary}"
    )
    ctx.step_started(emit, "verify", "verify.judge",
                     "LLM Retrieval Expert: judging before vs after citation-readiness",
                     agent="retrieval")
    try:
        judgement = await ctx.llm(
            system=CITATION_JUDGE, user=user, schema=CitationJudgement,
            max_tokens=3000, temperature=0.1,
        )
        for er in (*judgement.before, *judgement.after):
            er.status = SignalStatus.PREDICTED  # the judge only ever predicts
        delta = {}
        after_by_engine = {er.engine.value: er.score for er in judgement.after}
        for er in judgement.before:
            if er.engine.value in after_by_engine:
                delta[er.engine.value] = after_by_engine[er.engine.value] - er.score
        ctx.step_completed(emit, "verify", "verify.judge",
                           detail=judgement.summary,
                           meta={"agent": "retrieval", "counts": delta})
        return judgement
    except BudgetExceeded:
        ctx.step_skipped(emit, "verify", "verify.judge", "Citation judge",
                         detail="Skipped — LLM call budget reached.", meta={"agent": "retrieval"})
        return None
    except Exception as exc:
        ctx.step_failed(emit, "verify", "verify.judge", detail=str(exc),
                        meta={"agent": "retrieval"})
        return None


def apply_verification(
    blocks: list[RewriteBlock],
    issues_by_block: dict[str, list[VerificationIssue]],
    statuses: dict[str, str],
) -> VerificationReport:
    """Pure. Stamp each changed block's VerificationOutcome and roll up the report.
    statuses: block_id -> passed|revised|needs_human (unlisted changed blocks: passed
    unless they carry BLOCKING issues — advisory issues attach without blocking)."""
    report = VerificationReport()
    kinds: dict[str, int] = {}
    for b in blocks:
        if not b.changed:
            b.verification = None
            continue
        issues = issues_by_block.get(b.id, [])
        blocking = any(i.kind in BLOCKING_KINDS for i in issues)
        status = statuses.get(b.id) or ("needs_human" if blocking else "passed")
        b.verification = VerificationOutcome(status=status, issues=issues)
        if status == "passed":
            report.passed += 1
        elif status == "revised":
            report.revised += 1
        else:
            report.needs_human += 1
        report.issues_total += len(issues)
        for issue in issues:
            kinds[issue.kind] = kinds.get(issue.kind, 0) + 1
    report.by_kind = kinds
    return report
