"""AI Studio endpoints: generate a page rewrite and chat over it.

Routes live under /api/runs/{run_id}/... so the studio always operates on a saved run.
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.analysis.rewrite import chat_turn, flag_proposed_text, generate_rewrite
from app.analysis.schemas import AnalysisResult, PageRewrite, Recommendation
from app.ingestion.doc_parser import parse_document
from app.storage import repository

router = APIRouter(prefix="/api/runs", tags=["studio"])


class SelectOptionRequest(BaseModel):
    block_id: str
    index: int


async def _load_result(run_id: str) -> AnalysisResult:
    run = await repository.get_run(run_id)
    if not run or not run.result:
        raise HTTPException(status_code=404, detail="Run or result not found")
    return AnalysisResult.model_validate(run.result)


def _suggestions(state) -> list[dict]:
    return state.extra_recommendations if state else []


@router.get("/{run_id}/studio")
async def get_studio(run_id: str) -> dict:
    """Return the persisted studio state (rewrite + chat + suggestions) for reopening."""
    run = await repository.get_run(run_id)
    if not run or not run.result:
        raise HTTPException(status_code=404, detail="Run or result not found")
    state = await repository.get_studio_state(run_id)
    return {
        "rewrite": state.rewrite if state else None,
        "chat_history": state.chat_history if state else [],
        "extra_recommendations": _suggestions(state),
    }


@router.get("/{run_id}/snapshot")
async def get_snapshot(run_id: str) -> dict:
    """Return the sanitized HTML snapshot of the analyzed page for the Studio left pane."""
    run = await repository.get_run(run_id)
    if not run or not run.result:
        raise HTTPException(status_code=404, detail="Run or result not found")
    signals = run.result.get("page_signals") or {}
    return {
        "html": signals.get("snapshot_html", ""),
        "final_url": signals.get("final_url", run.url),
    }


@router.post("/{run_id}/rewrite")
async def create_rewrite(run_id: str, regenerate: bool = False) -> dict:
    """Generate (or return the cached) page rewrite for a run."""
    state = await repository.get_studio_state(run_id)
    if state and state.rewrite and not regenerate:
        return state.rewrite
    result = await _load_result(run_id)
    rewrite = await generate_rewrite(run_id, result)
    await repository.upsert_rewrite(run_id, rewrite)
    return rewrite.model_dump(mode="json")


@router.get("/{run_id}/rewrite")
async def fetch_rewrite(run_id: str) -> dict:
    state = await repository.get_studio_state(run_id)
    if not state or not state.rewrite:
        raise HTTPException(status_code=404, detail="No rewrite generated yet")
    return state.rewrite


@router.post("/{run_id}/chat")
async def chat(
    run_id: str,
    message: str = Form(...),
    block_id: str | None = Form(None),
    attachment: UploadFile | None = File(None),
) -> dict:
    """One chat turn (multipart): optional targeted block + optional attached document.

    Reply, apply any live block edits, append any new recommendations.
    """
    result = await _load_result(run_id)
    state = await repository.get_studio_state(run_id)
    rewrite = PageRewrite.model_validate(state.rewrite) if state and state.rewrite else None
    history = state.chat_history if state else []

    attachment_text = None
    attachment_note = ""
    if attachment is not None:
        data = await attachment.read()
        doc = parse_document(attachment.filename or "attachment", data)
        attachment_text = doc.text
        attachment_note = f" [attached: {doc.filename}]"

    response = await chat_turn(
        result, rewrite, history, message, block_id=block_id, attachment_text=attachment_text
    )

    await repository.append_chat(run_id, "user", message + attachment_note)
    await repository.append_chat(run_id, "assistant", response.reply)

    updated_rewrite = await repository.apply_block_edits(run_id, response.block_edits)
    suggestions: list[Recommendation] = []
    if response.new_recommendations:
        suggestions = await repository.add_recommendations(run_id, response.new_recommendations)

    return {
        "reply": response.reply,
        "rewrite": updated_rewrite.model_dump(mode="json") if updated_rewrite else None,
        "edited_block_ids": [e.block_id for e in response.block_edits],
        "new_recommendations": [s.model_dump(mode="json") for s in suggestions],
    }


@router.post("/{run_id}/select-option")
async def select_option(run_id: str, body: SelectOptionRequest) -> dict:
    """Set which of a content block's 3 options is active, re-flag it, return the rewrite."""
    state = await repository.get_studio_state(run_id)
    flags = None
    if state and state.rewrite:
        rw = PageRewrite.model_validate(state.rewrite)
        blk = next((b for b in rw.content_blocks if b.id == body.block_id), None)
        if blk and blk.options and 0 <= body.index < len(blk.options):
            flags = await flag_proposed_text(blk.options[body.index], rw.model_key)
    rewrite = await repository.select_block_option(run_id, body.block_id, body.index, flags)
    if rewrite is None:
        raise HTTPException(status_code=404, detail="Rewrite or block not found")
    return rewrite.model_dump(mode="json")
