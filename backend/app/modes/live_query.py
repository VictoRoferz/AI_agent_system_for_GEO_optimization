"""Mode 3 — Live query against real engines.

Sends each query to engines that expose citations via API and checks whether the
target domain appears in the cited sources. Observations are real (status OBSERVED).
Engines without a usable API (e.g. ChatGPT) are noted and left to prediction.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from app.analysis.schemas import EngineReadiness, SignalStatus, TargetEngine
from app.integrations import perplexity, serp
from app.modes.base import ModeContext, ModeOutput

# Engines we can observe live, mapped to their source-fetching coroutine.
_LIVE_SOURCES = {
    TargetEngine.PERPLEXITY: perplexity.cited_sources,
    TargetEngine.AI_OVERVIEWS: serp.ai_overview_sources,
}
_NO_LIVE_API = {TargetEngine.CHATGPT, TargetEngine.GEMINI}


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


async def _probe_engine(
    engine: TargetEngine, queries: list[str], target_domain: str
) -> tuple[EngineReadiness | None, str, list[str]]:
    fetch = _LIVE_SOURCES[engine]
    notes: list[str] = []
    cited_count = 0
    detail_lines: list[str] = []
    for q in queries:
        try:
            sources = await fetch(q)
        except RuntimeError as exc:  # missing key
            return None, "", [str(exc)]
        except Exception as exc:  # network / API error
            detail_lines.append(f"  - '{q}': error ({exc})")
            continue
        hit = any(_domain(s) == target_domain for s in sources)
        cited_count += int(hit)
        detail_lines.append(
            f"  - '{q}': {'CITED' if hit else 'not cited'} "
            f"({len(sources)} sources retrieved)"
        )
    total = len(queries) or 1
    score = round(100 * cited_count / total)
    readiness = EngineReadiness(
        engine=engine,
        score=score,
        status=SignalStatus.OBSERVED,
        rationale=f"Observed live: cited in {cited_count}/{total} queries.",
    )
    detail = f"### {engine.value} (live): cited in {cited_count}/{total} queries\n" + "\n".join(
        detail_lines
    )
    return readiness, detail, notes


async def run(ctx: ModeContext) -> ModeOutput:
    target_domain = _domain(ctx.page.final_url)
    queries = ctx.request.queries or []
    observed: list[EngineReadiness] = []
    details: list[str] = []
    notes: list[str] = []

    if not queries:
        notes.append("Live mode needs at least one query; none supplied.")

    probe_engines = [e for e in ctx.request.target_engines if e in _LIVE_SOURCES]
    results = await asyncio.gather(
        *(_probe_engine(e, queries, target_domain) for e in probe_engines)
    )
    for readiness, detail, engine_notes in results:
        notes.extend(engine_notes)
        if readiness:
            observed.append(readiness)
            details.append(detail)

    for e in ctx.request.target_engines:
        if e in _NO_LIVE_API:
            notes.append(
                f"{e.value} has no public citation API — not observable live; "
                "consider Simulation or Peec mode for it."
            )

    evidence = "## Live engine citation probes\n" + (
        "\n\n".join(details) if details else "(no live observations available)"
    )
    return ModeOutput(
        evidence_text=evidence,
        observed_engines=observed,
        notes=notes,
        mode_framing=(
            "Citation readiness for supported engines was OBSERVED by querying them live and "
            "checking whether the target domain appeared in the cited sources."
        ),
    )
