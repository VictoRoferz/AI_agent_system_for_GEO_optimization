"""Rewrite phase: every content block (batched fan-out), the technical changes,
and (full depth) net-new sections — all by ONE coordinated writer persona.

`validate_batch_coverage` makes full-page coverage a deterministic invariant:
whatever the model returns, every input block comes back exactly once.
"""
from __future__ import annotations

import asyncio

from app.agent.prompts import NEW_SECTIONS_WRITER, TECHNICAL_REWRITER, rewriter_system
from app.agent.schemas import OptimizationPlan, RewriteBatch
from app.analysis.rewrite import _finalize_blocks
from app.analysis.schemas import (
    Claim,
    PageSignals,
    Rationale,
    Recommendation,
    RewriteBlock,
    TextBlock,
)

_TAG_KIND = {"h1": "heading", "h2": "heading", "h3": "heading", "h4": "heading",
             "h5": "heading", "h6": "heading"}


def validate_batch_coverage(
    input_blocks: list[TextBlock], returned: list[RewriteBlock]
) -> list[RewriteBlock]:
    """Pure. Enforce the coverage contract: every input block exactly once
    (missing → keep-as-is backfill), duplicates dropped, `original` corrected to
    the true block text, unknown anchors discarded."""
    by_anchor: dict[str, RewriteBlock] = {}
    for blk in returned:
        if blk.anchor_id and blk.anchor_id not in by_anchor:
            by_anchor[blk.anchor_id] = blk
    out: list[RewriteBlock] = []
    for tb in input_blocks:
        blk = by_anchor.get(tb.id)
        if blk is None:
            out.append(
                RewriteBlock(
                    id="",  # assigned by _finalize_blocks
                    kind=_TAG_KIND.get(tb.tag, "paragraph"),
                    label=f"{tb.tag} block",
                    original=tb.text,
                    proposed=tb.text,
                    options=[tb.text],
                    anchor_id=tb.id,
                    rationale=Rationale(why="Not returned by the model; kept the original text."),
                )
            )
            continue
        blk.original = tb.text  # the page is the source of truth
        if not (blk.proposed or "").strip():
            blk.proposed = tb.text
            blk.options = [tb.text]
        if not blk.kind:
            blk.kind = _TAG_KIND.get(tb.tag, "paragraph")
        if not blk.label:
            blk.label = f"{tb.tag} block"
        out.append(blk)
    return out


def _recs_for_prompt(recs: list[Recommendation]) -> str:
    lines = []
    for r in recs:
        lines.append(f"- {r.id} [{r.priority.value}] {r.title}: {r.description}")
        if r.change and r.change.proposed_text:
            lines.append(f"    proposed copy: {r.change.proposed_text}")
    return "\n".join(lines) or "(none)"


def _claims_for_blocks(
    batch: list[TextBlock], claims_by_anchor: dict[str, list[Claim]]
) -> str:
    lines = []
    for tb in batch:
        for c in claims_by_anchor.get(tb.id, []):
            lines.append(f"- [{c.flag.value}] in {tb.id}: \"{c.text}\" — {c.rationale}")
    return "\n".join(lines) or "(none for these blocks)"


def _batch_user(
    page: PageSignals,
    batch: list[TextBlock],
    plan: OptimizationPlan,
    recs: list[Recommendation],
    claims_by_anchor: dict[str, list[Claim]],
    queries: list[str],
) -> str:
    plan_by_anchor = {p.anchor_id: p for p in plan.block_plan}
    block_lines = []
    for tb in batch:
        p = plan_by_anchor.get(tb.id)
        action = f" (plan: {p.action}{' — ' + p.reason if p.reason else ''})" if p else ""
        block_lines.append(f"- {tb.id} [{tb.tag}]{action}: {tb.text}")
    headings = ", ".join(page.headings[:20]) or "(none)"
    qs = "\n".join(f"- {q}" for q in queries) or "(none provided)"
    return (
        f"## Page context\nURL: {page.final_url}\nTitle: {page.title or '(none)'}\n"
        f"Headings: {headings}\n\n"
        f"## STYLE BRIEF (follow exactly)\n{plan.style_brief or '(none — keep the page voice)'}\n\n"
        f"## Blocks to rewrite (return EVERY id below exactly once)\n"
        + "\n".join(block_lines)
        + f"\n\n## Recommendations to implement (reference their ids in rationale)\n{_recs_for_prompt(recs)}\n\n"
        f"## Unresolved claim risks in these blocks (MUST be resolved)\n"
        f"{_claims_for_blocks(batch, claims_by_anchor)}\n\n"
        f"## Target queries\n{qs}"
    )


def _technical_user(
    page: PageSignals, plan: OptimizationPlan, recs: list[Recommendation]
) -> str:
    tech_recs = [r for r in recs if r.change and r.change.change_type.value == "technical"]
    schema_types = ", ".join(page.schema_types) or "(none)"
    return (
        f"## Page signals\nURL: {page.final_url}\nTitle: {page.title or '(none)'}\n"
        f"Meta description: {page.meta_description or '(none)'}\n"
        f"Canonical: {page.canonical or '(none)'}\n"
        f"Has JSON-LD: {page.has_jsonld} | schema types: {schema_types}\n"
        f"Author: {page.has_author} | published: {page.published_date or '-'} | "
        f"modified: {page.modified_date or '-'}\n\n"
        f"## Planned technical work\n"
        + ("\n".join(f"- {t}" for t in plan.technical_plan) or "(none planned)")
        + f"\n\n## Technical recommendations to implement\n{_recs_for_prompt(tech_recs)}\n\n"
        f"## Main text (for accurate schema values — use ONLY facts present here)\n"
        f"{page.main_text[:8000]}"
    )


def _sections_user(page: PageSignals, plan: OptimizationPlan, queries: list[str]) -> str:
    wanted = "\n".join(
        f"- {s.label} (placement: {s.placement_hint}) — {s.reason}" for s in plan.new_sections
    )
    qs = "\n".join(f"- {q}" for q in queries) or "(none provided)"
    return (
        f"## STYLE BRIEF (follow exactly)\n{plan.style_brief}\n\n"
        f"## Sections to write\n{wanted}\n\n"
        f"## Target queries\n{qs}\n\n"
        f"## Page main text (the ONLY source of facts)\n{page.main_text[:12000]}"
    )


async def run_rewrite(
    ctx, emit, plan: OptimizationPlan, recs: list[Recommendation],
    claims_by_anchor: dict[str, list[Claim]],
) -> tuple[list[RewriteBlock], list[RewriteBlock]]:
    """Returns (content_blocks, technical_blocks), finalized with stable blk-N ids."""
    from app.agent.budget import partition_blocks

    batches = partition_blocks(
        ctx.page.text_blocks, ctx.depth.rewrite_batch_blocks, ctx.depth.rewrite_batch_chars
    )
    sem = asyncio.Semaphore(ctx.depth.concurrency)
    system = rewriter_system(ctx.depth.options_per_block)

    async def one(idx: int, batch: list[TextBlock]) -> list[RewriteBlock]:
        step_id = f"rewrite.b{idx}"
        ctx.step_started(
            emit, "rewrite", step_id,
            f"Rewriting blocks {batch[0].id}–{batch[-1].id}",
            agent="strategist",
            meta={"block_ids": [b.id for b in batch]},
        )
        try:
            async with sem:
                rb = await ctx.llm(
                    system=system,
                    user=_batch_user(ctx.page, batch, plan, recs, claims_by_anchor, ctx.result.queries),
                    schema=RewriteBatch,
                    max_tokens=12000,  # full batch text + options + rationales; truncation kills JSON
                    temperature=0.3,
                )
            blocks = validate_batch_coverage(batch, rb.blocks)
            changed = sum(1 for b in blocks if " ".join(b.proposed.split()) != " ".join(b.original.split()))
            ctx.step_completed(
                emit, "rewrite", step_id,
                meta={"agent": "strategist", "counts": {"blocks": len(blocks), "changed": changed}},
            )
            return blocks
        except Exception as exc:
            ctx.step_failed(emit, "rewrite", step_id, detail=str(exc), meta={"agent": "strategist"})
            return validate_batch_coverage(batch, [])  # keep-as-is fallback, page stays covered

    content_groups = await asyncio.gather(*(one(i + 1, b) for i, b in enumerate(batches)))
    content_blocks = [b for g in content_groups for b in g]

    # Technical changes — Technical GEO Engineer, one call.
    technical_blocks: list[RewriteBlock] = []
    ctx.step_started(emit, "rewrite", "rewrite.technical",
                     "Producing technical changes (JSON-LD, meta, canonical)", agent="technical")
    try:
        async with sem:
            tb = await ctx.llm(
                system=TECHNICAL_REWRITER,
                user=_technical_user(ctx.page, plan, recs),
                schema=RewriteBatch,
                max_tokens=4000,
                temperature=0.1,
            )
        technical_blocks = tb.blocks
        ctx.step_completed(emit, "rewrite", "rewrite.technical",
                           meta={"agent": "technical", "counts": {"changes": len(technical_blocks)}})
    except Exception as exc:
        ctx.step_failed(emit, "rewrite", "rewrite.technical", detail=str(exc), meta={"agent": "technical"})

    # Net-new sections — full depth only.
    if ctx.depth.net_new_sections and plan.new_sections:
        ctx.step_started(emit, "rewrite", "rewrite.new-sections",
                         f"Writing {len(plan.new_sections)} net-new sections", agent="strategist")
        try:
            async with sem:
                nb = await ctx.llm(
                    system=NEW_SECTIONS_WRITER,
                    user=_sections_user(ctx.page, plan, ctx.result.queries),
                    schema=RewriteBatch,
                    max_tokens=4000,
                    temperature=0.3,
                )
            fresh = [b for b in nb.blocks if not b.anchor_id]  # net-new must be unanchored
            content_blocks.extend(fresh)
            ctx.step_completed(emit, "rewrite", "rewrite.new-sections",
                               meta={"agent": "strategist", "counts": {"sections": len(fresh)}})
        except Exception as exc:
            ctx.step_failed(emit, "rewrite", "rewrite.new-sections", detail=str(exc),
                            meta={"agent": "strategist"})

    nxt = _finalize_blocks(content_blocks, 1, technical=False)
    _finalize_blocks(technical_blocks, nxt, technical=True)
    return content_blocks, technical_blocks
