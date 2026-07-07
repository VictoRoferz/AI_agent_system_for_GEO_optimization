"""AI Studio brain: generate a full page rewrite and run chat turns over it.

`generate_rewrite` turns a finished AnalysisResult into a block-by-block proposed
rewrite (reader-facing content + technical code changes), each block carrying the
original, the proposed version and a plain-language explanation of the change.

`chat_turn` answers a user question about the page / recommendations / GenAI
visibility and, when asked, returns block edits (applied live to the right pane)
and/or new recommendations.
"""
from __future__ import annotations

import re

from app.analysis.schemas import (
    AnalysisResult,
    ChatResponse,
    LLMRewrite,
    PageRewrite,
    ProposedFlag,
    ProposedFlagList,
    Recommendation,
    RewriteBlock,
)
from app.core.llm import complete_structured
from app.ingestion.kb_loader import load_kb_context

_REWRITE_SYSTEM = """You are a senior GEO (Generative Engine Optimization) content engineer. \
You are given a web page's current content and signals plus a prioritized set of \
recommendations. Produce a COMPLETE proposed rewrite of the page that applies those \
recommendations so AI search engines (ChatGPT, Google AI Overviews, Perplexity, Gemini) are \
far more likely to CITE it — while preserving the page's real meaning, facts and intent. \
Never invent facts that aren't supported by the original page.

REGULATED-INDUSTRY COMPLIANCE — ALWAYS APPLY. Treat the page as regulated pharma / medtech / \
biotech / healthcare content. Every word you propose must be compliant: no unsubstantiated \
promotional or marketing language; every efficacy, safety, superiority or outcome claim must \
be backed by a citable study, clinical data or regulatory approval present on the page — if \
the evidence is not there, do NOT assert the claim (state it factually, add a citation \
placeholder, or soften it). Avoid absolute/comparative claims ("best", "cure", "guaranteed", \
"#1", "superior to X") without head-to-head evidence, and avoid off-label implications. If the \
original text contains a non-compliant claim, rewrite it into a compliant version and explain \
that in `change_explanation`.

Return two sets of blocks:
  * content_blocks — the reader-facing copy: the title, key headings and the main \
paragraphs. For EVERY content block, fill `options` with EXACTLY 3 distinct, ready-to-publish \
rewrites, in this order: (1) most conservative / most-compliant (closest to the original, \
safest claims), (2) balanced (clear GEO improvement, still careful), (3) concise & punchy but \
still fully compliant. All three must obey the compliance rules above. Set `proposed` equal to \
`options[0]`. Quote the `original` verbatim (use "" if it is net-new), set is_technical=false, \
and give a short plain-language `change_explanation` (what changed across the options and why it \
helps AI citation). \
ALSO fill `flags` for option 1 (the `proposed` text): list EVERY factual statement, claim, or \
NUMBER / STATISTIC / DATE in it that a reader could ask "is that proven?". For each, set \
`quote` = the EXACT substring copied verbatim from `proposed`, `flag` ("red" = needs a study/ \
citation and none is shown — efficacy/safety/superiority/comparative claims or unsourced \
numbers; "yellow" = factual but should cite a source; "green" = established common-knowledge \
fact, no proof needed), and `note` = what proof would substantiate it. Quotes MUST appear \
verbatim in `proposed`; cover numbers, percentages and dates explicitly. \
REQUIRED: every content block that corresponds to existing page text MUST have a non-null \
`anchor_id` chosen from the "Page content blocks" list below (e.g. "g7"), and you must copy \
that block's text into `original` VERBATIM. Only a genuinely net-new block (no matching page \
text) may have anchor_id = null. Do not leave anchor_id null for a block whose text exists on \
the page — pick the closest matching id.
  * technical_blocks — exact code changes: JSON-LD/schema, meta/link tags, canonical, etc. \
For each, put any existing markup in `original` ("" if net-new), the EXACT code to ship in \
`proposed`, set is_technical=true, leave `options` empty, set a clear `label` (e.g. "JSON-LD \
Article schema"), and explain why it matters in `change_explanation`.

Write a concise `summary` of the rewrite strategy. Use stable ids like "blk-1", "blk-2"."""

_CHAT_SYSTEM = """You are the Syte GEO Studio agent. You ITERATE with the user on ONE web \
page's PROPOSED rewrite. Your job is to actually CHANGE the proposed content when asked — not \
just talk about it. You return structured output: `reply` (always, short), `block_edits` (when \
you change content), and `new_recommendations` (only when explicitly asked for page-level ideas).

THE GOLDEN RULE — when the user asks to change content, the new text MUST appear in \
`block_edits`, NEVER only described in `reply`. A reply like "Here's a new recommendation: …" \
with empty block_edits is WRONG and useless — the user sees no change. If they asked for a \
change, `block_edits` must be non-empty.

WHEN TO EDIT A BLOCK (return a `block_edits` entry):
  * A "## Targeted block" id means the user is working on THAT block. If they ask to change it \
in ANY way — "rewrite it", "another version", "a different option", "make another", "shorter", \
"punchier", "more compliant", "use the attached document", "add X", "do it", "apply", "change \
it" — you MUST return a `block_edits` entry for that block_id with the FULL new text in \
`proposed` AND `options` = 3 fresh distinct compliant variants (conservative / balanced / \
punchy), proposed = option 1, plus a one-line `change_explanation`. Keep `reply` to a short \
confirmation ("Updated the intro — here are 3 new options."). ALSO set `flags` for the new \
option-1 text: every factual statement / claim / number that needs proof, each with `quote` \
(verbatim substring), `flag` (red/yellow/green) and `note` (what proof).
  * If no targeted block is given but the user names/points at a block, edit it the same way \
(find its block_id in the list).

WHEN TO EXPLAIN (no block_edits): if the user asks WHY the content is recommended, what changed, \
or any question — answer fully in `reply`, block_edits empty.

WHEN TO ADD RECOMMENDATIONS: only if the user explicitly asks for new PAGE-LEVEL recommendations \
(not editing this block) — return them in `new_recommendations`, each concrete (fill `change`).

ATTACHED DOCUMENT — treat "## Attached document" as PRIMARY EVIDENCE the user provided (a study, \
guideline, data, brief — any document). Embed its relevant findings into the new block text with \
appropriate attribution, and reflect that in `block_edits`. Don't contradict it; flag conflicts \
in `reply`.

REGULATED-INDUSTRY COMPLIANCE — ALWAYS APPLY. Treat the page as regulated pharma / medtech / \
biotech / healthcare content. Any copy you propose must be compliant: no unsubstantiated \
promotional language; no efficacy/safety/superiority/outcome claim without citable study, \
clinical data or regulatory approval; avoid absolute/comparative claims and off-label \
implications. If the user asks for non-compliant copy, propose a compliant alternative and say \
why in `reply`."""


_FLAG_SYSTEM = """You flag a single piece of PROPOSED web copy for a regulated pharma / medtech \
/ healthcare page. List EVERY factual statement, claim, or NUMBER / STATISTIC / DATE in the text \
that a reader could reasonably ask "is that proven?". For each, return `quote` = the EXACT \
substring copied verbatim from the text, `flag` ("red" = needs a study/citation and none is \
shown — efficacy/safety/superiority/comparative claims or unsourced numbers/percentages; \
"yellow" = factual but should cite a source; "green" = established common-knowledge fact, no \
proof needed), and `note` = the proof that would substantiate it (e.g. "peer-reviewed study", \
"FDA approval", "cite the source"). Quotes MUST appear verbatim so the UI can highlight them. \
Never invent sources or numbers. Skip purely promotional filler with no factual content."""


async def flag_proposed_text(proposed: str, model_key: str | None) -> list[ProposedFlag]:
    """(Re)flag a single proposed text: which statements/numbers need proof. Best-effort."""
    if not (proposed or "").strip():
        return []
    try:
        res = await complete_structured(
            system=_FLAG_SYSTEM,
            user=f"## Proposed text\n{proposed}",
            schema=ProposedFlagList,
            model_key=model_key,
            max_tokens=1500,
        )
        # Keep only flags whose quote actually appears in the text (so they can highlight).
        return [f for f in res.flags if f.quote and f.quote in proposed]
    except Exception:
        return []


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def _signals_block(result: AnalysisResult) -> str:
    p = result.page_signals
    if not p:
        return "## Page\n(no signals captured)"
    headings = "\n".join(f"  - {h}" for h in p.headings[:30]) or "  (none)"
    return (
        f"## Page signals\n"
        f"URL: {p.final_url}\n"
        f"Title: {p.title or '(none)'}\n"
        f"Meta description: {p.meta_description or '(none)'}\n"
        f"Canonical: {p.canonical or '(none)'}\n"
        f"Has JSON-LD: {p.has_jsonld} | schema types: {', '.join(p.schema_types) or '(none)'}\n"
        f"Author: {p.has_author} | published: {p.published_date or '-'} | "
        f"modified: {p.modified_date or '-'}\n"
        f"Headings:\n{headings}\n\n"
        f"## Main text (extracted)\n{p.main_text[:12000]}"
    )


def _page_blocks(result: AnalysisResult) -> str:
    blocks = result.page_signals.text_blocks if result.page_signals else []
    if not blocks:
        return "## Page content blocks\n(none captured — leave anchor_id null)"
    lines = [f"- {b.id} [{b.tag}]: {b.text}" for b in blocks]
    return (
        "## Page content blocks (anchor each content rewrite to one of these ids)\n"
        + "\n".join(lines)
    )


def _recs_block(recs: list[Recommendation]) -> str:
    if not recs:
        return "## Recommendations\n(none)"
    lines = []
    for r in recs:
        lines.append(f"- [{r.priority}] {r.title}: {r.description}")
        if r.change and r.change.proposed_text:
            lines.append(f"    proposed copy: {r.change.proposed_text}")
        if r.change and r.change.code_snippet:
            lines.append(f"    proposed code: {r.change.code_snippet}")
    return "## Recommendations to apply\n" + "\n".join(lines)


def _words(text: str) -> set[str]:
    """Word tokens (length>3) for fuzzy matching — robust to punctuation/em-dashes."""
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 3}


def _resolve_anchors(blocks: list[RewriteBlock], text_blocks) -> None:
    """Deterministically backfill missing `anchor_id`s by fuzzily matching each block's
    `original` against the page's tagged text blocks (word overlap) — so the studio preview
    reflects EVERY block, not only the ones the model happened to anchor."""
    if not text_blocks:
        return
    tb = [(t.id, _words(t.text)) for t in text_blocks]
    tb = [(tid, w) for tid, w in tb if w]
    for blk in blocks:
        if blk.anchor_id or not blk.original.strip():
            continue
        ow = _words(blk.original)
        if len(ow) < 4:
            continue
        best_id, best_score = None, 0.0
        for tid, tw in tb:
            score = len(ow & tw) / max(1, min(len(ow), len(tw)))
            if score > best_score:
                best_id, best_score = tid, score
        if best_id and best_score >= 0.5:  # half the shorter block's distinctive words overlap
            blk.anchor_id = best_id


def _finalize_blocks(blocks: list[RewriteBlock], start: int, technical: bool) -> int:
    """Assign stable ids, force is_technical, normalize options, compute changed. Returns next id."""
    idx = start
    for b in blocks:
        b.id = f"blk-{idx}"
        b.is_technical = technical
        if not technical:
            # Content blocks carry 3 style options; keep proposed in sync with the active one.
            if not b.options:
                b.options = [b.proposed] if b.proposed else []
            b.selected_option_index = 0
            if b.options:
                b.proposed = b.options[0]
        else:
            b.options = []
            b.flags = []
        b.changed = _norm(b.proposed) != _norm(b.original)
        idx += 1
    return idx


async def generate_rewrite(run_id: str, result: AnalysisResult) -> PageRewrite:
    user = (
        f"{_signals_block(result)}\n\n"
        f"{_page_blocks(result)}\n\n"
        f"{_recs_block(result.recommendations)}\n\n"
        f"User queries the page should win citations for:\n"
        + ("\n".join(f"- {q}" for q in result.queries) or "(none)")
    )
    llm = await complete_structured(
        system=_REWRITE_SYSTEM,
        user=user,
        schema=LLMRewrite,
        model_key=result.model_key,
        cache_prefix=load_kb_context() or None,
        max_tokens=8000,
    )
    nxt = _finalize_blocks(llm.content_blocks, 1, technical=False)
    _finalize_blocks(llm.technical_blocks, nxt, technical=True)
    _resolve_anchors(
        llm.content_blocks, result.page_signals.text_blocks if result.page_signals else []
    )
    return PageRewrite(
        run_id=run_id,
        summary=llm.summary,
        content_blocks=llm.content_blocks,
        technical_blocks=llm.technical_blocks,
        model_key=result.model_key,
    )


def _rewrite_block_listing(rewrite: PageRewrite) -> str:
    lines = []
    for b in (*rewrite.content_blocks, *rewrite.technical_blocks):
        kind = "technical" if b.is_technical else "content"
        lines.append(f"- {b.id} ({kind}, {b.label}): {b.proposed[:200]}")
    return "\n".join(lines) or "(no blocks yet)"


async def chat_turn(
    result: AnalysisResult,
    rewrite: PageRewrite | None,
    history: list[dict],
    message: str,
    block_id: str | None = None,
    attachment_text: str | None = None,
) -> ChatResponse:
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in history[-12:]) or "(start of conversation)"
    blocks = _rewrite_block_listing(rewrite) if rewrite else "(rewrite not generated yet)"
    target = f"## Targeted block\n{block_id}\n\n" if block_id else ""
    attachment = (
        f"## Attached document (primary evidence the user provided)\n{attachment_text[:12000]}\n\n"
        if attachment_text
        else ""
    )
    user = (
        f"{_signals_block(result)}\n\n"
        f"{_recs_block(result.recommendations)}\n\n"
        f"## Current proposed rewrite blocks (edit these by block_id)\n{blocks}\n\n"
        f"{target}"
        f"{attachment}"
        f"## Conversation so far\n{convo}\n\n"
        f"## New user message\n{message}"
    )
    return await complete_structured(
        system=_CHAT_SYSTEM,
        user=user,
        schema=ChatResponse,
        model_key=result.model_key,
        cache_prefix=load_kb_context() or None,
        max_tokens=4000,
    )
