"""Audit phase: the expert panel checks the page against every canonical KB factor.

Fan-out: one call per expert over its owned factor categories (quick depth merges
expert pairs). LLM proposes audits/findings; everything else here is deterministic:
quote sanitization, factor backfill, cross-expert dedup, coverage computation.
"""
from __future__ import annotations

import asyncio
import re

from app.agent.prompts import EXPERTS, auditor_system
from app.agent.schemas import FactorAudit, FactorAuditBatch, KBFactor, KBFactorSet
from app.analysis.claims import extract_claims
from app.analysis.schemas import (
    AnalysisResult,
    Claim,
    KBCoverageItem,
    KBCoverageStatus,
    LLMFinding,
    PageSignals,
    Recommendation,
    RewriteBlock,
)
from app.analysis.signals import summarize_signals

_WORD_RE = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if len(w) > 3}


def _audit_user(result: AnalysisResult, page: PageSignals, goals_text: str | None) -> str:
    blocks = "\n".join(f"- {b.id} [{b.tag}]: {b.text}" for b in page.text_blocks) or "(none)"
    queries = "\n".join(f"- {q}" for q in result.queries) or "(none provided)"
    observed = [
        f"- {er.engine.value}: {er.score}/100 ({er.status.value}) — {er.rationale}"
        for er in result.engine_readiness
    ]
    goals = f"\n\n## Strategic goals (excerpt)\n{goals_text[:2000]}" if goals_text else ""
    return (
        f"{summarize_signals(page)}\n\n"
        f"## Page content blocks (anchor evidence quotes to these ids)\n{blocks}\n\n"
        f"## User queries the page should win citations for\n{queries}\n\n"
        f"## Prior engine readiness\n" + ("\n".join(observed) or "(none)") + goals
    )


def sanitize_audits(
    audits: list[FactorAudit],
    expected: list[KBFactor],
    page: PageSignals,
    agent_id: str,
) -> list[FactorAudit]:
    """Pure. Enforce the audit contract: only expected factor ids (first entry wins),
    every expected factor present (missing → status=error), evidence quotes verbatim
    on the page (invalid quotes dropped), findings stamped with the expert id."""
    block_texts = {b.id: b.text for b in page.text_blocks}
    haystack = (page.main_text or "") + " " + " ".join(block_texts.values())
    by_id: dict[str, FactorAudit] = {}
    valid_ids = {f.id for f in expected}
    for audit in audits:
        if audit.factor_id not in valid_ids or audit.factor_id in by_id:
            continue
        kept_quotes = []
        for q in audit.evidence_quotes:
            text = (q.quote or "").strip()
            if not text:
                continue
            if q.source != "page" or text in haystack:
                kept_quotes.append(q.model_copy(update={"quote": text[:240]}))
        audit.evidence_quotes = kept_quotes
        if audit.status not in ("covered", "partial", "gap"):
            audit.status = "gap"
        for f in audit.findings:
            f.source_agent = agent_id
            if audit.factor_id not in f.rationale.kb_factor_ids:
                f.rationale.kb_factor_ids.insert(0, audit.factor_id)
        by_id[audit.factor_id] = audit
    out: list[FactorAudit] = []
    for f in expected:
        out.append(
            by_id.get(f.id)
            or FactorAudit(factor_id=f.id, status="error", assessment="Not returned by the auditor.")
        )
    return out


async def run_audits(ctx, emit) -> tuple[list[FactorAudit], list[Claim]]:
    """Expert-panel fan-out + (if absent) concurrent claim extraction."""
    from app.agent.budget import expert_audit_partitions

    partitions = expert_audit_partitions(ctx.factor_set.factors, ctx.depth)
    total = len(ctx.factor_set.factors)
    done_counter = {"n": 0}
    sem = asyncio.Semaphore(ctx.depth.concurrency)
    user = _audit_user(ctx.result, ctx.page, ctx.goals_text)

    async def one(idx: int, expert_ids: list[str], factors: list[KBFactor]) -> list[FactorAudit]:
        step_id = f"audit.g{idx}"
        lead = expert_ids[0]
        names = " + ".join(EXPERTS[e].name for e in expert_ids)
        ctx.step_started(
            emit, "audit", step_id, f"{names}: auditing {len(factors)} factors",
            agent=lead, meta={"factors_total": total, "factors_done": done_counter["n"]},
        )
        try:
            async with sem:
                batch = await ctx.llm(
                    system=auditor_system(expert_ids, factors),
                    user=user,
                    schema=FactorAuditBatch,
                    max_tokens=6000,
                    temperature=0.1,
                )
            audits = sanitize_audits(batch.audits, factors, ctx.page, lead)
            findings = [f for a in audits for f in a.findings]
            done_counter["n"] += len(factors)
            ctx.step_completed(
                emit, "audit", step_id,
                meta={
                    "agent": lead,
                    "factors_done": done_counter["n"],
                    "factors_total": total,
                    "counts": {"findings": len(findings), "gaps": sum(1 for a in audits if a.status == "gap")},
                    "findings": [f.title for f in findings],
                },
            )
            return audits
        except Exception as exc:
            done_counter["n"] += len(factors)
            ctx.step_failed(emit, "audit", step_id, detail=str(exc), meta={"agent": lead})
            return [
                FactorAudit(factor_id=f.id, status="error", assessment=f"Audit call failed: {exc}")
                for f in factors
            ]

    claims_task = None
    if not ctx.result.claims:
        ctx.step_started(emit, "audit", "audit.claims", "Extracting factual claims", agent="compliance")
        claims_task = asyncio.create_task(
            extract_claims(ctx.request, ctx.page, ctx.goals, ctx.kb_context)
        )

    groups = await asyncio.gather(*(one(i + 1, e, f) for i, (e, f) in enumerate(partitions)))
    audits = [a for g in groups for a in g]

    claims: list[Claim] = list(ctx.result.claims)
    if claims_task is not None:
        try:
            claims = await claims_task
            ctx.step_completed(
                emit, "audit", "audit.claims",
                meta={"agent": "compliance", "counts": {"claims": len(claims)}},
            )
        except Exception as exc:
            ctx.step_failed(emit, "audit", "audit.claims", detail=str(exc), meta={"agent": "compliance"})
            claims = []
    if all(a.status == "error" for a in audits):
        raise RuntimeError("Every audit call failed — aborting the optimization run.")
    return audits, claims


def merge_audit_findings(audits: list[FactorAudit]) -> list[LLMFinding]:
    """Pure. Cross-expert dedup: same normalized change-target + title word-overlap
    ≥ 0.6 → keep the higher-impact finding, union its kb_factor_ids."""
    merged: list[LLMFinding] = []
    for audit in audits:
        for finding in audit.findings:
            fw = _words(finding.title)
            target = (finding.change.target if finding.change else "").strip().lower()
            dup = None
            for kept in merged:
                kt = (kept.change.target if kept.change else "").strip().lower()
                if target and kt and target != kt:
                    continue
                kw = _words(kept.title)
                overlap = len(fw & kw) / max(1, min(len(fw), len(kw)))
                if overlap >= 0.6:
                    dup = kept
                    break
            if dup is None:
                merged.append(finding)
            else:
                winner = finding if finding.impact_score > dup.impact_score else dup
                loser = dup if winner is finding else finding
                if winner is not dup:
                    merged[merged.index(dup)] = winner
                if winner.rationale and loser.rationale:
                    for fid in loser.rationale.kb_factor_ids:
                        if fid not in winner.rationale.kb_factor_ids:
                            winner.rationale.kb_factor_ids.append(fid)
    return merged


def coverage_from_audits(
    audits: list[FactorAudit],
    factor_set: KBFactorSet,
    recs: list[Recommendation],
    blocks: list[RewriteBlock] | None = None,
) -> list[KBCoverageItem]:
    """Pure. One coverage row per canonical factor, linked to the recs that address
    it (via rationale.kb_factor_ids) and the rewrite blocks that implement it."""
    names = {f.id: f.name for f in factor_set.factors}
    audit_by_id = {a.factor_id: a for a in audits}
    rec_ids_by_factor: dict[str, list[str]] = {}
    for rec in recs:
        for fid in (rec.rationale.kb_factor_ids if rec.rationale else []):
            rec_ids_by_factor.setdefault(fid, []).append(rec.id)
    block_ids_by_factor: dict[str, list[str]] = {}
    for b in blocks or []:
        if not b.changed or not b.rationale:
            continue
        for fid in b.rationale.kb_factor_ids:
            block_ids_by_factor.setdefault(fid, []).append(b.id)

    out: list[KBCoverageItem] = []
    for f in factor_set.factors:
        audit = audit_by_id.get(f.id)
        status = KBCoverageStatus.GAP
        assessment = "Audit unavailable for this factor."
        if audit is not None and audit.status in ("covered", "partial", "gap"):
            status = KBCoverageStatus(audit.status)
            assessment = audit.assessment or assessment
        elif audit is not None:
            assessment = audit.assessment or assessment
        out.append(
            KBCoverageItem(
                factor=names.get(f.id, f.id),
                factor_id=f.id,
                status=status,
                assessment=assessment,
                related_rec_ids=rec_ids_by_factor.get(f.id, []),
                related_block_ids=block_ids_by_factor.get(f.id, []),
            )
        )
    return out


def claims_by_anchor(claims: list[Claim]) -> dict[str, list[Claim]]:
    """Pure. Red/yellow claims grouped by page block, for the rewrite prompts."""
    out: dict[str, list[Claim]] = {}
    for c in claims:
        if c.flag.value in ("red", "yellow") and c.anchor_id:
            out.setdefault(c.anchor_id, []).append(c)
    return out
