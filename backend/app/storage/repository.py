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
from app.storage.models import AgentRun, AgentTrace, ContentCache, KBFactorCache, Run, StudioState


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
            if edit.options:
                block.options = edit.options
            sel = edit.selected_index if edit.selected_index is not None else 0
            block.selected_option_index = sel if block.options and 0 <= sel < len(block.options) else 0
            block.proposed = (
                block.options[block.selected_option_index] if block.options else edit.proposed
            )
            if edit.flags:
                block.flags = edit.flags
            block.change_explanation = edit.change_explanation
            block.changed = _norm(block.proposed) != _norm(block.original)
        else:
            new_block = RewriteBlock(
                id=f"blk-{next_idx}",
                kind="paragraph",
                label=edit.label or "New block",
                original="",
                proposed=edit.options[0] if edit.options else edit.proposed,
                options=edit.options,
                flags=edit.flags,
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


async def select_block_option(
    run_id: str, block_id: str, index: int, flags=None
) -> PageRewrite | None:
    """Set a content block's active option (proposed = options[index]); persist and return.

    `flags` (if given) replaces the block's inline evidence flags for the new option.
    """
    async with async_session_maker() as session:
        state = await session.get(StudioState, run_id)
        if state is None or not state.rewrite:
            return None
        rewrite = PageRewrite.model_validate(state.rewrite)
        for b in rewrite.content_blocks:
            if b.id == block_id and b.options and 0 <= index < len(b.options):
                b.selected_option_index = index
                b.proposed = b.options[index]
                if flags is not None:
                    b.flags = flags
                b.changed = _norm(b.proposed) != _norm(b.original)
                break
        else:
            return rewrite
        state.rewrite = rewrite.model_dump(mode="json")
        state.updated_at = _utcnow()
        await session.commit()
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


# ---------------------------------------------------------------- agent (optimize)
async def get_factor_set(kb_hash: str):
    """Cached canonical KB factor set for this KB content hash, if any."""
    from app.agent.schemas import KBFactorSet  # local import to avoid cycles

    async with async_session_maker() as session:
        row = await session.get(KBFactorCache, kb_hash)
        return KBFactorSet.model_validate(row.payload) if row and row.payload else None


async def save_factor_set(fs) -> None:
    async with async_session_maker() as session:
        await session.merge(
            KBFactorCache(
                kb_hash=fs.kb_hash,
                model_key=fs.model_key,
                payload=fs.model_dump(mode="json"),
            )
        )
        await session.commit()


async def get_agent_run(run_id: str) -> AgentRun | None:
    async with async_session_maker() as session:
        return await session.get(AgentRun, run_id)


async def save_agent_run(
    run_id: str,
    status: str,
    depth: str,
    model_key: str,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    async with async_session_maker() as session:
        existing = await session.get(AgentRun, run_id)
        row = existing or AgentRun(run_id=run_id)
        row.status = status
        row.depth = depth
        row.model_key = model_key
        row.result = result
        row.error = error
        row.updated_at = _utcnow()
        await session.merge(row)
        await session.commit()


async def get_agent_trace(run_id: str) -> AgentTrace | None:
    async with async_session_maker() as session:
        return await session.get(AgentTrace, run_id)


async def upsert_agent_trace(
    run_id: str,
    *,
    status: str,
    depth: str,
    model_key: str,
    steps: list[dict],
    summary: dict | None = None,
) -> None:
    """Upserted on each step transition so the trace is readable MID-RUN."""
    async with async_session_maker() as session:
        existing = await session.get(AgentTrace, run_id)
        row = existing or AgentTrace(run_id=run_id)
        row.status = status
        row.depth = depth
        row.model_key = model_key
        row.steps = steps
        if summary is not None:
            row.summary = summary
        row.updated_at = _utcnow()
        await session.merge(row)
        await session.commit()
