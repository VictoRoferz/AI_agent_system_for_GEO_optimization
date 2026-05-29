"""Mode 4 — GEO-factor + knowledge-base analysis.

Evidence is the deterministic page-signal briefing. Engine readiness is left to the
brain to predict (status = PREDICTED) during synthesis, grounded in the KB pillars.
"""
from __future__ import annotations

from app.analysis.signals import heuristic_baseline, summarize_signals
from app.modes.base import ModeContext, ModeOutput


async def run(ctx: ModeContext) -> ModeOutput:
    briefing = summarize_signals(ctx.page)
    baseline = heuristic_baseline(ctx.page)
    return ModeOutput(
        evidence_text=(
            f"{briefing}\n\n"
            f"(Objective heuristic citability baseline: {baseline}/100 — for reference only; "
            f"use the knowledge base to form the authoritative judgement.)"
        ),
        notes=[],
        mode_framing=(
            "Analysis based on known GEO/AEO ranking factors and the internal knowledge base. "
            "Engine citation readiness is PREDICTED from page structure, not observed live."
        ),
    )
