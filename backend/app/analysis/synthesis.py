"""Shared synthesis step — fuse mode evidence into one AnalysisResult via the brain."""
from __future__ import annotations

from app.analysis.prioritization import prioritize
from app.analysis.schemas import (
    AnalysisRequest,
    AnalysisResult,
    EngineReadiness,
    GoalsDocument,
    LLMAnalysis,
    PageSignals,
)
from app.core.llm import complete_structured
from app.modes.base import ModeOutput

_SYSTEM = """You are a senior Generative Engine Optimization (GEO) strategist producing a \
management-consulting-grade analysis. Your job: assess whether AI search engines \
(ChatGPT, Google AI Overviews, Perplexity, Gemini) would CITE the given page for the user's \
queries, and whether the page communicates what the strategic goals intend.

Ground every judgement in the knowledge base (if provided) and the extracted page signals.
Be specific, critical and actionable. For each recommendation provide: what to do, WHY it \
matters for AI citation/visibility, the expected impact, an impact_score (1-5), an effort \
level, and a confidence (1-5). Prefer a focused set of high-leverage recommendations over a \
long shallow list. Reference concrete evidence from the page.

You will also score citation readiness (0-100) per requested target engine and assess \
goal alignment and query coverage."""


def _goals_block(goals: GoalsDocument | None) -> str:
    if not goals or not goals.text:
        return "## Strategic goals\n(none provided)"
    return f"## Strategic goals (from {goals.filename})\n{goals.text[:8000]}"


def _merge_engine_readiness(
    predicted: list[EngineReadiness], observed: list[EngineReadiness]
) -> list[EngineReadiness]:
    """Observed (real/live/simulated) values win over brain predictions per engine."""
    merged = {er.engine: er for er in predicted}
    for er in observed:
        merged[er.engine] = er
    return list(merged.values())


async def synthesize(
    request: AnalysisRequest,
    page: PageSignals,
    goals: GoalsDocument | None,
    kb_context: str,
    mode_output: ModeOutput,
) -> AnalysisResult:
    queries = "\n".join(f"- {q}" for q in request.queries) or "(none provided)"
    engines = ", ".join(e.value for e in request.target_engines) or "(none)"
    user = (
        f"## Analysis mode\n{mode_output.mode_framing}\n\n"
        f"## Target AI engines to score\n{engines}\n\n"
        f"## User queries\n{queries}\n\n"
        f"{_goals_block(goals)}\n\n"
        f"## Evidence gathered for this mode\n{mode_output.evidence_text}\n"
    )

    llm = await complete_structured(
        system=_SYSTEM,
        user=user,
        schema=LLMAnalysis,
        model_key=request.model_key,
        cache_prefix=kb_context or None,
        max_tokens=6000,
    )

    engine_readiness = _merge_engine_readiness(llm.engine_readiness, mode_output.observed_engines)
    recommendations = prioritize(llm.findings)

    return AnalysisResult(
        executive_summary=llm.executive_summary,
        overall_score=llm.overall_score,
        engine_readiness=engine_readiness,
        alignment=llm.alignment,
        recommendations=recommendations,
        url=page.final_url,
        queries=request.queries,
        mode=request.mode,
        model_key=request.model_key or "claude-default",
        target_engines=request.target_engines,
        page_signals=page,
        notes=mode_output.notes,
    )
