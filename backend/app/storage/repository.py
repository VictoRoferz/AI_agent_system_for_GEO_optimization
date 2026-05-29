"""Persistence helpers for runs and the content cache."""
from __future__ import annotations

from sqlalchemy import select

from app.analysis.schemas import AnalysisRequest, AnalysisResult, PageSignals
from app.storage.db import async_session_maker
from app.storage.models import ContentCache, Run


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
