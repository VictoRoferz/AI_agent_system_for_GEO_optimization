"""Mode 2 — Simulation. The brain role-plays each target engine.

For each selected engine we ask the brain to answer the user's queries *as that engine
would*, then judge whether the target URL/domain would be cited. Engines are processed
concurrently. Results are PREDICTED (no real engine is contacted).
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.analysis.schemas import EngineReadiness, SignalStatus, TargetEngine
from app.core.llm import complete_structured
from app.modes.base import ModeContext, ModeOutput

_ENGINE_PERSONA = {
    TargetEngine.CHATGPT: "ChatGPT with web browsing (cites a small set of authoritative sources)",
    TargetEngine.AI_OVERVIEWS: "Google AI Overviews (synthesizes top-ranking pages, cites several)",
    TargetEngine.PERPLEXITY: "Perplexity (answer engine that cites many sources inline)",
    TargetEngine.GEMINI: "Google Gemini with search grounding",
}


class _QueryVerdict(BaseModel):
    query: str
    would_cite: bool
    reasoning: str


class _SimResult(BaseModel):
    readiness_score: int = Field(ge=0, le=100)
    rationale: str
    verdicts: list[_QueryVerdict] = Field(default_factory=list)


async def _simulate_engine(ctx: ModeContext, engine: TargetEngine) -> tuple[EngineReadiness, str]:
    persona = _ENGINE_PERSONA.get(engine, engine.value)
    domain = urlparse(ctx.page.final_url).netloc
    queries = "\n".join(f"- {q}" for q in ctx.request.queries) or "- (no queries provided)"
    system = (
        f"You are simulating {persona}. Given a candidate web page, decide for each query "
        f"whether you would cite this page (URL: {ctx.page.final_url}, domain: {domain}) when "
        "answering. Be realistic and critical: only cite genuinely authoritative, relevant, "
        "well-structured content. Then give an overall 0-100 citation-readiness score."
    )
    user = (
        f"PAGE TITLE: {ctx.page.title}\n"
        f"PAGE CONTENT (truncated):\n{ctx.page.main_text[:8000]}\n\n"
        f"QUERIES:\n{queries}"
    )
    result = await complete_structured(
        system=system,
        user=user,
        schema=_SimResult,
        model_key=ctx.request.model_key,
        cache_prefix=ctx.kb_context or None,
    )
    cited = sum(1 for v in result.verdicts if v.would_cite)
    total = len(result.verdicts) or 1
    detail = (
        f"### {engine.value}: predicted readiness {result.readiness_score}/100 "
        f"({cited}/{total} queries would cite)\n{result.rationale}\n"
        + "\n".join(f"  - [{'CITE' if v.would_cite else 'skip'}] {v.query}: {v.reasoning}"
                    for v in result.verdicts)
    )
    return (
        EngineReadiness(
            engine=engine,
            score=result.readiness_score,
            status=SignalStatus.PREDICTED,
            rationale=result.rationale,
        ),
        detail,
    )


async def run(ctx: ModeContext) -> ModeOutput:
    engines = ctx.request.target_engines or [TargetEngine.CHATGPT]
    results = await asyncio.gather(*(_simulate_engine(ctx, e) for e in engines))
    observed = [r[0] for r in results]
    evidence = "## Simulated engine answers\n" + "\n\n".join(r[1] for r in results)
    return ModeOutput(
        evidence_text=evidence,
        observed_engines=observed,
        mode_framing=(
            "Citation readiness was estimated by role-playing each AI engine answering the "
            "queries (simulation). Treat as an informed prediction, not observed behaviour."
        ),
    )
