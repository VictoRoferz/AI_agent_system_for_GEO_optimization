"""History endpoints: list past runs and fetch a single run."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response

from app.analysis.schemas import AnalysisResult
from app.export.markdown import render_markdown
from app.export.pdf import render_pdf
from app.storage import repository

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("")
async def list_runs() -> list[dict]:
    runs = await repository.list_runs()
    out = []
    for r in runs:
        result = r.result or {}
        out.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "url": r.url,
                "mode": r.mode,
                "model_key": r.model_key,
                "status": r.status,
                "overall_score": result.get("overall_score"),
                "goals_filename": r.goals_filename,
            }
        )
    return out


@router.get("/{run_id}")
async def get_run(run_id: str) -> dict:
    run = await repository.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat(),
        "url": run.url,
        "mode": run.mode,
        "model_key": run.model_key,
        "status": run.status,
        "queries": run.queries,
        "target_engines": run.target_engines,
        "goals_filename": run.goals_filename,
        "result": run.result,
        "error": run.error,
    }


@router.get("/{run_id}/export")
async def export_run(run_id: str, format: str = "md"):
    run = await repository.get_run(run_id)
    if not run or not run.result:
        raise HTTPException(status_code=404, detail="Run or result not found")
    result = AnalysisResult.model_validate(run.result)
    if format == "md":
        return PlainTextResponse(
            render_markdown(result),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="geo-report-{run_id}.md"'},
        )
    if format == "pdf":
        pdf = await render_pdf(result)
        return Response(
            pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="geo-report-{run_id}.pdf"'},
        )
    raise HTTPException(status_code=400, detail="format must be 'md' or 'pdf'")
