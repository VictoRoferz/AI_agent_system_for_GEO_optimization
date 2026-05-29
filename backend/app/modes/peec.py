"""Mode 1 — Peec AI data. Pull real tracked visibility/citation metrics for the domain.

When Peec covers the domain we surface observed per-engine metrics; otherwise we add a
clear note and let synthesis fall back to a prediction.
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.analysis.schemas import EngineReadiness, SignalStatus, TargetEngine
from app.integrations import peec
from app.modes.base import ModeContext, ModeOutput

# Map common Peec model/engine identifiers onto our TargetEngine enum.
_ENGINE_ALIASES = {
    "chatgpt": TargetEngine.CHATGPT,
    "openai": TargetEngine.CHATGPT,
    "gpt": TargetEngine.CHATGPT,
    "ai_overviews": TargetEngine.AI_OVERVIEWS,
    "google": TargetEngine.AI_OVERVIEWS,
    "google_aio": TargetEngine.AI_OVERVIEWS,
    "perplexity": TargetEngine.PERPLEXITY,
    "gemini": TargetEngine.GEMINI,
}


def _to_score(value) -> int | None:
    """Peec metrics are 0-1 ratios; convert to 0-100. Pass through if already 0-100."""
    if not isinstance(value, (int, float)):
        return None
    return round(value * 100) if value <= 1 else round(min(value, 100))


async def run(ctx: ModeContext) -> ModeOutput:
    domain = urlparse(ctx.page.final_url).netloc.lower().removeprefix("www.")
    report = await peec.domain_report(domain)

    if report is None:
        return ModeOutput(
            evidence_text="## Peec AI\nNo Peec data available for this domain.",
            notes=[
                f"Peec AI returned no data for '{domain}' "
                "(not tracked, or PEEC_API_KEY not configured). "
                "Falling back to predicted readiness."
            ],
            mode_framing="Peec data unavailable; readiness below is PREDICTED, not observed.",
        )

    observed: list[EngineReadiness] = []
    lines = [f"## Peec AI report for {domain}"]
    by_engine = report.get("by_engine") or report.get("models") or {}
    if isinstance(by_engine, dict):
        items = by_engine.items()
    else:  # list of {engine/model, visibility, ...}
        items = ((d.get("engine") or d.get("model"), d) for d in by_engine)

    for raw_key, metrics in items:
        engine = _ENGINE_ALIASES.get(str(raw_key).lower())
        if not engine or not isinstance(metrics, dict):
            continue
        score = _to_score(metrics.get("visibility") or metrics.get("citation_rate"))
        if score is None:
            continue
        observed.append(
            EngineReadiness(
                engine=engine,
                score=score,
                status=SignalStatus.OBSERVED,
                rationale=f"Peec-tracked visibility/citation metric: {score}/100.",
            )
        )
        lines.append(f"- {engine.value}: {score}/100 (observed by Peec)")

    return ModeOutput(
        evidence_text="\n".join(lines),
        observed_engines=observed,
        notes=[] if observed else ["Peec report had no recognizable per-engine metrics."],
        mode_framing="Citation readiness is OBSERVED from Peec AI's real tracking data.",
    )
