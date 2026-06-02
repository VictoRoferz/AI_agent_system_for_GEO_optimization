"""Drives one analysis run, emitting progress events then the final result."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.analysis.claims import compliance_score, extract_claims
from app.analysis.schemas import AnalysisRequest, AnalysisResult, GoalsDocument, ProgressEvent
from app.analysis.synthesis import synthesize
from app.ingestion.kb_loader import load_kb_context
from app.ingestion.url_fetcher import fetch_page
from app.modes import MODE_HANDLERS
from app.modes.base import ModeContext


async def run_analysis(
    request: AnalysisRequest, goals: GoalsDocument | None
) -> AsyncIterator[tuple[str, object]]:
    """Yield ('progress', ProgressEvent) tuples, then a final ('result', AnalysisResult)."""
    yield "progress", ProgressEvent(step="fetch", message="Fetching and rendering the page…", pct=10)
    page = await fetch_page(request.url)

    yield "progress", ProgressEvent(step="kb", message="Loading GEO knowledge base…", pct=30)
    kb_context = load_kb_context()

    handler = MODE_HANDLERS[request.mode]
    yield "progress", ProgressEvent(
        step="mode", message=f"Running {request.mode.value} analysis mode…", pct=45
    )
    mode_output = await handler(ModeContext(request=request, page=page, goals=goals, kb_context=kb_context))

    yield "progress", ProgressEvent(
        step="synthesis", message="Synthesizing findings & checking factual claims…", pct=75
    )
    # Recommendations and the claim/evidence check are independent — run them concurrently.
    result, claims = await asyncio.gather(
        synthesize(request, page, goals, kb_context, mode_output),
        extract_claims(request, page, goals, kb_context),
    )
    result.claims = claims
    result.compliance_score = compliance_score(claims)

    yield "progress", ProgressEvent(step="done", message="Analysis complete.", pct=100)
    yield "result", result
