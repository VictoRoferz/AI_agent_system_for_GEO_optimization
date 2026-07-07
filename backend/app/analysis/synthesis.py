"""Shared synthesis step — fuse mode evidence into one AnalysisResult via the brain."""
from __future__ import annotations

from app.analysis.prioritization import prioritize, rank_order
from app.analysis.schemas import (
    AnalysisRequest,
    AnalysisResult,
    EngineReadiness,
    GoalsDocument,
    KBCoverageItem,
    LLMAnalysis,
    PageSignals,
)
from app.core.llm import complete_structured
from app.core.prompt_blocks import COMPLIANCE_BLOCK, CONCRETE_CHANGE_BLOCK
from app.modes.base import ModeOutput

_SYSTEM = f"""You are a senior Generative Engine Optimization (GEO) strategist producing a \
management-consulting-grade analysis. Your job: assess whether AI search engines \
(ChatGPT, Google AI Overviews, Perplexity, Gemini) would CITE the given page for the user's \
queries, and whether the page communicates what the strategic goals intend.

Ground every judgement in the knowledge base (if provided) and the extracted page signals.
Be specific, critical and actionable. For each recommendation provide: what to do, WHY it \
matters for AI citation/visibility, the expected impact, an impact_score (1-5), an effort \
level, and a confidence (1-5). Reference concrete evidence from the page.

BE EXHAUSTIVE — systematically evaluate the page against EVERY factor/pillar in the knowledge \
base. Produce a recommendation for every genuine, KB-grounded gap or improvement; there is NO \
cap on the number of recommendations. Do not pad with trivia, but omit nothing real. Order \
does not matter (priority is assigned downstream).

{COMPLIANCE_BLOCK}

{CONCRETE_CHANGE_BLOCK}

You will also score citation readiness (0-100) per requested target engine and assess \
goal alignment and query coverage.

KB COVERAGE CHECKLIST — derive the list of distinct factors/pillars from the knowledge base \
and, in `kb_coverage`, return ONE item per factor so the user can see every factor was \
considered. For each: `factor` (the factor name), `status` ("covered" | "partial" | "gap"), a \
one-line `assessment` of how the page does, and `related_rec_ids` listing the finding(s) that \
address it — reference each finding by its 1-based position in your `findings` list (e.g. \
"1", "3"). Leave `related_rec_ids` empty for fully covered factors with no needed change."""


def _goals_block(goals: GoalsDocument | None) -> str:
    if not goals or not goals.text:
        return "## Strategic goals\n(none provided)"
    return f"## Strategic goals (from {goals.filename})\n{goals.text[:8000]}"


def _remap_kb_coverage(
    items: list[KBCoverageItem], findings: list
) -> list[KBCoverageItem]:
    """Translate KB-coverage `related_rec_ids` (1-based finding positions from the brain)
    into the final `rec-N` ids assigned by prioritization."""
    order = rank_order(findings)  # order[rank] = original finding index
    orig_to_recid = {orig: f"rec-{rank + 1}" for rank, orig in enumerate(order)}
    out: list[KBCoverageItem] = []
    for item in items:
        mapped: list[str] = []
        for ref in item.related_rec_ids:
            token = str(ref).strip().lstrip("#").removeprefix("rec-").removeprefix("finding-")
            try:
                orig = int(token) - 1
            except ValueError:
                continue
            rid = orig_to_recid.get(orig)
            if rid and rid not in mapped:
                mapped.append(rid)
        out.append(
            KBCoverageItem(
                factor=item.factor,
                status=item.status,
                assessment=item.assessment,
                related_rec_ids=mapped,
            )
        )
    return out


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
        max_tokens=10000,
    )

    engine_readiness = _merge_engine_readiness(llm.engine_readiness, mode_output.observed_engines)
    recommendations = prioritize(llm.findings)
    kb_coverage = _remap_kb_coverage(llm.kb_coverage, llm.findings)

    return AnalysisResult(
        executive_summary=llm.executive_summary,
        overall_score=llm.overall_score,
        engine_readiness=engine_readiness,
        alignment=llm.alignment,
        recommendations=recommendations,
        kb_coverage=kb_coverage,
        url=page.final_url,
        queries=request.queries,
        mode=request.mode,
        model_key=request.model_key or "claude-default",
        target_engines=request.target_engines,
        page_signals=page,
        notes=mode_output.notes,
    )
