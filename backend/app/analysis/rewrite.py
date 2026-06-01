"""AI Studio brain: generate a full page rewrite and run chat turns over it.

`generate_rewrite` turns a finished AnalysisResult into a block-by-block proposed
rewrite (reader-facing content + technical code changes), each block carrying the
original, the proposed version and a plain-language explanation of the change.

`chat_turn` answers a user question about the page / recommendations / GenAI
visibility and, when asked, returns block edits (applied live to the right pane)
and/or new recommendations.
"""
from __future__ import annotations

from app.analysis.schemas import (
    AnalysisResult,
    ChatResponse,
    LLMRewrite,
    PageRewrite,
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

Return two sets of blocks:
  * content_blocks — the reader-facing copy: the title, key headings and the main \
paragraphs. For each, quote the `original` verbatim (use "" if it is net-new), write the \
concrete `proposed` rewrite (ready to publish, not a description), set is_technical=false, \
and give a short plain-language `change_explanation` a non-technical user understands \
(what changed and why it helps AI citation). If a block is unchanged, set proposed equal to \
original and explain it was kept.
  * technical_blocks — exact code changes: JSON-LD/schema, meta/link tags, canonical, etc. \
For each, put any existing markup in `original` ("" if net-new), the EXACT code to ship in \
`proposed`, set is_technical=true, set a clear `label` (e.g. "JSON-LD Article schema"), and \
explain why it matters in `change_explanation`.

Write a concise `summary` of the rewrite strategy. Use stable ids like "blk-1", "blk-2"."""

_CHAT_SYSTEM = """You are the GEO Studio agent for one specific web page. You help the user \
improve how likely AI search engines are to cite this page. You can:
  * answer questions about the page, the recommendations, and GenAI/AI-search visibility, \
grounded in the page signals and the knowledge base;
  * when the user asks to change the proposed rewrite, return `block_edits` — each targets an \
existing block by its `block_id` (see the current blocks below) or uses block_id="new" to add \
one (then also set `label` and `is_technical`). Put the full new text/code in `proposed` and a \
short plain-language `change_explanation`. Only edit what the user asked about;
  * when the user asks for more or different recommendations, return them in \
`new_recommendations`, each concrete (fill the `change` object: a content rewrite or an exact \
technical code change with instructions), with impact_score, effort and confidence.

Always write a helpful `reply`. Leave `block_edits` and `new_recommendations` empty when the \
user only asked a question."""


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


def _finalize_blocks(blocks: list[RewriteBlock], start: int, technical: bool) -> int:
    """Assign stable ids, force is_technical, and compute the changed flag. Returns next id."""
    idx = start
    for b in blocks:
        b.id = f"blk-{idx}"
        b.is_technical = technical
        b.changed = _norm(b.proposed) != _norm(b.original)
        idx += 1
    return idx


async def generate_rewrite(run_id: str, result: AnalysisResult) -> PageRewrite:
    user = (
        f"{_signals_block(result)}\n\n"
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
) -> ChatResponse:
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in history[-12:]) or "(start of conversation)"
    blocks = _rewrite_block_listing(rewrite) if rewrite else "(rewrite not generated yet)"
    user = (
        f"{_signals_block(result)}\n\n"
        f"{_recs_block(result.recommendations)}\n\n"
        f"## Current proposed rewrite blocks (edit these by block_id)\n{blocks}\n\n"
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
