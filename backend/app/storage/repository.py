"""Persistence helpers for runs, the content cache and AI Studio state."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.analysis.prioritization import prioritize
from app.analysis.schemas import (
    AnalysisRequest,
    AnalysisResult,
    BlockEdit,
    LLMFinding,
    PageRewrite,
    PageSignals,
    Recommendation,
    RewriteBlock,
)
from app.storage.db import async_session_maker
from app.storage.models import ContentCache, Run, StudioState


async def save_run(
    run_id: str,
    request: AnalysisRequest,
    goals_filename: str | None,
    result: AnalysisResult | None,
    error: str | None = None,
) -> None:
    async with async_session_maker() as session:
        run = Run(
            id=run_id,
            url=request.url,
            mode=request.mode.value,
            model_key=request.model_key or "claude-default",
            status="error" if error else "completed",
            queries=request.queries,
            target_engines=[e.value for e in request.target_engines],
            goals_filename=goals_filename,
            result=result.model_dump(mode="json") if result else None,
            error=error,
        )
        await session.merge(run)
        await session.commit()


async def list_runs(limit: int = 100) -> list[Run]:
    async with async_session_maker() as session:
        rows = await session.execute(select(Run).order_by(Run.created_at.desc()).limit(limit))
        return list(rows.scalars().all())


async def get_run(run_id: str) -> Run | None:
    async with async_session_maker() as session:
        return await session.get(Run, run_id)


async def get_cached_signals(cache_key: str) -> PageSignals | None:
    async with async_session_maker() as session:
        row = await session.get(ContentCache, cache_key)
        return PageSignals.model_validate(row.payload) if row else None


async def cache_signals(cache_key: str, signals: PageSignals) -> None:
    async with async_session_maker() as session:
        await session.merge(
            ContentCache(cache_key=cache_key, payload=signals.model_dump(mode="json"))
        )
        await session.commit()


# --------------------------------------------------------------------- AI Studio
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _suggestions(findings: list[LLMFinding]) -> list[Recommendation]:
    """Prioritize chat-proposed findings into recommendations with stable, distinct ids."""
    recs = prioritize(findings)
    for i, rec in enumerate(recs, start=1):
        rec.id = f"sug-{i}"
    return recs


async def get_studio_state(run_id: str) -> StudioState | None:
    async with async_session_maker() as session:
        return await session.get(StudioState, run_id)


async def _load_or_new(session, run_id: str) -> StudioState:
    state = await session.get(StudioState, run_id)
    if state is None:
        state = StudioState(run_id=run_id)
        session.add(state)
    return state


async def upsert_rewrite(run_id: str, rewrite: PageRewrite) -> None:
    async with async_session_maker() as session:
        state = await _load_or_new(session, run_id)
        state.rewrite = rewrite.model_dump(mode="json")
        state.updated_at = _utcnow()
        await session.commit()


async def append_chat(run_id: str, role: str, content: str) -> None:
    async with async_session_maker() as session:
        state = await _load_or_new(session, run_id)
        # Reassign (not .append) so SQLAlchemy detects the JSON column change.
        state.chat_history = [*(state.chat_history or []), {"role": role, "content": content}]
        state.updated_at = _utcnow()
        await session.commit()


def apply_edits_to_rewrite(rewrite: PageRewrite, edits: list[BlockEdit]) -> PageRewrite:
    """Pure: apply chat-driven block edits to a rewrite (update existing or add new)."""
    by_id = {b.id: b for b in (*rewrite.content_blocks, *rewrite.technical_blocks)}
    next_idx = len(by_id) + 1
    for edit in edits:
        block = by_id.get(edit.block_id)
        if block is not None:
            block.proposed = edit.proposed
            block.change_explanation = edit.change_explanation
            block.changed = _norm(block.proposed) != _norm(block.original)
        else:
            new_block = RewriteBlock(
                id=f"blk-{next_idx}",
                kind="paragraph",
                label=edit.label or "New block",
                original="",
                proposed=edit.proposed,
                changed=True,
                is_technical=edit.is_technical,
                change_explanation=edit.change_explanation,
            )
            next_idx += 1
            if edit.is_technical:
                rewrite.technical_blocks.append(new_block)
            else:
                rewrite.content_blocks.append(new_block)
    return rewrite


async def apply_block_edits(run_id: str, edits: list[BlockEdit]) -> PageRewrite | None:
    """Apply chat-driven edits to the stored rewrite and return the updated rewrite."""
    if not edits:
        state = await get_studio_state(run_id)
        return PageRewrite.model_validate(state.rewrite) if state and state.rewrite else None
    async with async_session_maker() as session:
        state = await session.get(StudioState, run_id)
        if state is None or not state.rewrite:
            return None
        rewrite = apply_edits_to_rewrite(PageRewrite.model_validate(state.rewrite), edits)
        state.rewrite = rewrite.model_dump(mode="json")
        state.updated_at = _utcnow()
        await session.commit()
        return rewrite


async def add_recommendations(run_id: str, findings: list[LLMFinding]) -> list[Recommendation]:
    """Append chat-proposed findings to the run's studio suggestions; return the full list."""
    async with async_session_maker() as session:
        state = await _load_or_new(session, run_id)
        existing = [LLMFinding.model_validate(f) for f in (state.extra_recommendations or [])]
        combined = _suggestions([*existing, *findings])
        state.extra_recommendations = [r.model_dump(mode="json") for r in combined]
        state.updated_at = _utcnow()
        await session.commit()
        return combined


def _norm(text: str) -> str:
    return " ".join((text or "").split())
