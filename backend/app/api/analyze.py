"""POST /api/analyze — run an analysis, streaming progress over SSE.

Uses multipart/form-data so the strategic-goals document can be uploaded alongside the
JSON fields. The response is a text/event-stream; the frontend reads it via fetch()
(not EventSource, which is GET-only).
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from app.analysis.orchestrator import run_analysis
from app.analysis.schemas import (
    AnalysisMode,
    AnalysisRequest,
    AnalysisResult,
    ProgressEvent,
    TargetEngine,
)
from app.ingestion.doc_parser import parse_document
from app.storage import repository

router = APIRouter(prefix="/api", tags=["analyze"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _parse_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except json.JSONDecodeError:
        pass
    # fall back to comma-separated
    return [v.strip() for v in value.split(",") if v.strip()]


@router.post("/analyze")
async def analyze(
    url: str = Form(...),
    queries: str | None = Form(None),
    mode: str = Form(AnalysisMode.GEO_FACTORS.value),
    target_engines: str | None = Form(None),
    model_key: str | None = Form(None),
    goals_file: UploadFile | None = File(None),
):
    # Parse the strategic-goals document up-front (so parse errors surface immediately).
    goals = None
    goals_filename = None
    if goals_file is not None:
        data = await goals_file.read()
        goals = parse_document(goals_file.filename or "goals", data)
        goals_filename = goals.filename

    engine_keys = _parse_list(target_engines) or [
        TargetEngine.CHATGPT.value,
        TargetEngine.AI_OVERVIEWS.value,
    ]
    request = AnalysisRequest(
        url=url,
        queries=_parse_list(queries),
        mode=AnalysisMode(mode),
        target_engines=[TargetEngine(e) for e in engine_keys],
        model_key=model_key or None,
    )
    run_id = uuid.uuid4().hex[:12]

    async def stream() -> AsyncIterator[str]:
        yield _sse("run", {"run_id": run_id})
        result: AnalysisResult | None = None
        try:
            async for kind, payload in run_analysis(request, goals):
                if kind == "progress":
                    yield _sse("progress", ProgressEvent.model_validate(payload).model_dump())
                elif kind == "result":
                    result = payload  # type: ignore[assignment]
            assert result is not None
            await repository.save_run(run_id, request, goals_filename, result)
            # The snapshot HTML is persisted with the run but kept out of the streamed
            # payload (it can be ~600 KB); the Studio fetches it via /runs/{id}/snapshot.
            payload = result.model_dump(mode="json", exclude={"page_signals": {"snapshot_html"}})
            yield _sse("result", {"run_id": run_id, **payload})
        except Exception as exc:  # surface failures to the UI and persist the error
            await repository.save_run(run_id, request, goals_filename, None, error=str(exc))
            yield _sse("error", {"run_id": run_id, "message": str(exc)})

    return StreamingResponse(stream(), media_type="text/event-stream")
