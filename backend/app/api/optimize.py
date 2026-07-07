"""Optimization-agent endpoints: run the agent (SSE), read its trace/result, KB factors.

POST /api/runs/{run_id}/optimize   — run the multi-phase agent over a saved analysis run
GET  /api/runs/{run_id}/optimization — the stored OptimizationResult (+ status)
GET  /api/runs/{run_id}/trace       — the persisted step timeline (readable MID-RUN)
GET  /api/kb/factors                — the canonical KB factor list (dev/QA)
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.agent.assemble import assemble_page, render_change_package
from app.agent.engine import run_optimization
from app.agent.events import sse_payload
from app.agent.factors import get_factor_set
from app.agent.schemas import OptimizationResult
from app.analysis.schemas import (
    AnalysisMode,
    AnalysisRequest,
    AnalysisResult,
    PageRewrite,
    TargetEngine,
)
from app.api.sse import sse, with_heartbeat
from app.config import get_settings
from app.ingestion.doc_parser import parse_document
from app.ingestion.kb_loader import load_kb_context
from app.storage import repository

router = APIRouter(prefix="/api", tags=["agent"])


async def _load_run_result(run_id: str) -> tuple[object, AnalysisResult]:
    run = await repository.get_run(run_id)
    if run is None or not run.result:
        raise HTTPException(status_code=404, detail="Run not found or has no result")
    return run, AnalysisResult.model_validate(run.result)


@router.post("/runs/{run_id}/optimize")
async def optimize(
    run_id: str,
    depth: str | None = None,
    regenerate: bool = False,
    model_key: str | None = Form(None),
    goals_file: UploadFile | None = File(None),
):
    settings = get_settings()
    depth_key = depth if depth in ("quick", "full") else settings.agent_default_depth
    run, result = await _load_run_result(run_id)

    signals = result.page_signals
    if signals is None or not signals.text_blocks:
        raise HTTPException(
            status_code=409,
            detail="This run predates snapshot capture — re-run the analysis first.",
        )
    if not load_kb_context():
        raise HTTPException(
            status_code=409,
            detail="Knowledge base is empty — add pillar documents to Knowledge_base/ "
            "and restart the backend.",
        )

    goals = None
    if goals_file is not None:
        data = await goals_file.read()
        goals = parse_document(goals_file.filename or "goals", data)

    engines = [TargetEngine(e) for e in (run.target_engines or [])]
    request = AnalysisRequest(
        url=run.url,
        queries=list(run.queries or []),
        mode=AnalysisMode(run.mode),
        target_engines=engines or [TargetEngine.CHATGPT, TargetEngine.AI_OVERVIEWS],
        model_key=run.model_key,
    )
    chosen_model = model_key or run.model_key

    # Idempotent replay: an existing completed optimization streams back instantly.
    existing = await repository.get_agent_run(run_id)
    if existing is not None and existing.status == "completed" and existing.result and not regenerate:
        async def replay() -> AsyncIterator[str]:
            yield sse("run", {"run_id": run_id})
            trace = await repository.get_agent_trace(run_id)
            for step in (trace.steps if trace else []):
                yield sse("agent_step", step)
            from app.agent.engine import _slim_result

            yield sse("result", _slim_result(OptimizationResult.model_validate(existing.result)))
        return StreamingResponse(replay(), media_type="text/event-stream")

    async def stream() -> AsyncIterator[str]:
        yield sse("run", {"run_id": run_id})
        try:
            async for kind, payload in run_optimization(
                run_id, request, result, depth_key, chosen_model, goals
            ):
                if kind == "agent_step":
                    yield sse("agent_step", sse_payload(payload))
                elif kind == "progress":
                    yield sse("progress", payload.model_dump())
                elif kind == "result":
                    yield sse("result", {"run_id": run_id, **payload})
        except Exception as exc:
            yield sse("error", {"run_id": run_id, "message": str(exc)})

    return StreamingResponse(with_heartbeat(stream()), media_type="text/event-stream")


@router.get("/runs/{run_id}/optimization")
async def get_optimization(run_id: str):
    row = await repository.get_agent_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No optimization for this run")
    return {
        "run_id": run_id,
        "status": row.status,
        "depth": row.depth,
        "model_key": row.model_key,
        "result": row.result,
        "error": row.error,
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("/runs/{run_id}/trace")
async def get_trace(run_id: str, kind: str = "optimize"):
    row = await repository.get_agent_trace(run_id)
    if row is None or row.kind != kind:
        raise HTTPException(status_code=404, detail="No trace for this run")
    return {
        "run_id": run_id,
        "kind": row.kind,
        "status": row.status,
        "depth": row.depth,
        "model_key": row.model_key,
        "started_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "events": row.steps,
        "summary": row.summary,
    }


async def _load_export_inputs(run_id: str) -> tuple[object, PageRewrite]:
    run, _ = await _load_run_result(run_id)
    state = await repository.get_studio_state(run_id)
    if state is None or not state.rewrite:
        raise HTTPException(status_code=404, detail="No rewrite to export — run the optimization first.")
    return run, PageRewrite.model_validate(state.rewrite)


@router.get("/runs/{run_id}/export-page")
async def export_page(run_id: str, include: str = "verified", deployable: bool = False):
    """The final optimized page as a deployable HTML file (assembled deterministically)."""
    run, rewrite = await _load_export_inputs(run_id)
    snapshot = (run.result.get("page_signals") or {}).get("snapshot_html", "")
    if not snapshot:
        raise HTTPException(status_code=409, detail="No snapshot captured — re-run the analysis.")
    assembled = assemble_page(
        snapshot, rewrite, include="all" if include == "all" else "verified", deployable=deployable
    )
    return Response(
        content=assembled.html,
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="optimized-{run_id}.html"',
            "X-Applied-Blocks": str(len(assembled.applied_block_ids)),
            "X-Skipped-Blocks": str(len(assembled.skipped_block_ids)),
        },
    )


@router.get("/runs/{run_id}/change-package")
async def change_package(run_id: str):
    """Markdown package: every change + why + verification + code + manual steps."""
    run, rewrite = await _load_export_inputs(run_id)
    agent_run = await repository.get_agent_run(run_id)
    if agent_run is None or not agent_run.result:
        raise HTTPException(status_code=404, detail="No optimization result — run the agent first.")
    optimization = OptimizationResult.model_validate(agent_run.result)
    snapshot = (run.result.get("page_signals") or {}).get("snapshot_html", "")
    not_applied = assemble_page(snapshot, rewrite).not_applied if snapshot else []
    md = render_change_package(optimization, rewrite, run.url, not_applied)
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="change-package-{run_id}.md"'},
    )


@router.get("/kb/factors")
async def kb_factors(refresh: bool = False):
    """The canonical KB factor list (extracted once per KB content hash, then cached)."""
    kb = load_kb_context()
    if not kb:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base is empty — add pillar documents to Knowledge_base/ "
            "and restart the backend.",
        )
    try:
        fs = await get_factor_set(kb, model_key=get_settings().default_model, refresh=refresh)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return fs.model_dump(mode="json")
