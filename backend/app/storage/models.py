"""SQLModel tables: persisted analysis runs and a fetched-content cache."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column
from sqlalchemy.types import JSON, Text
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Run(SQLModel, table=True):
    id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    url: str
    mode: str
    model_key: str
    status: str = "completed"  # completed | error
    # Inputs and the full AnalysisResult are stored as JSON blobs.
    queries: list = Field(default_factory=list, sa_column=Column(JSON))
    target_engines: list = Field(default_factory=list, sa_column=Column(JSON))
    goals_filename: str | None = None
    result: dict | None = Field(default=None, sa_column=Column(JSON))
    error: str | None = Field(default=None, sa_column=Column(Text))


class ContentCache(SQLModel, table=True):
    """Hash-keyed cache of fetched URL signals to avoid refetching."""
    cache_key: str = Field(primary_key=True)  # sha256 of the URL
    created_at: datetime = Field(default_factory=_utcnow)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))


class StudioState(SQLModel, table=True):
    """Per-run AI Studio state: the generated rewrite, chat history and any
    extra recommendations the chat agent proposed. A separate table so it is
    created by `create_all` without altering the existing Run table."""
    run_id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    rewrite: dict | None = Field(default=None, sa_column=Column(JSON))
    chat_history: list = Field(default_factory=list, sa_column=Column(JSON))  # [{role, content}]
    extra_recommendations: list = Field(default_factory=list, sa_column=Column(JSON))


class KBFactorCache(SQLModel, table=True):
    """Canonical KB factor list, cached per KB-content hash.

    KB edits change the hash → automatic invalidation; the payload is a
    KBFactorSet dump. Sibling table (create_all, no migration)."""
    kb_hash: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow)
    model_key: str = ""
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))


class AgentRun(SQLModel, table=True):
    """One optimization-agent run over an analysis run: the OptimizationResult
    (audits, recommendations, coverage, verification, before/after scores).
    The PageRewrite itself lives in StudioState.rewrite so the studio stack
    keeps working on agent output unchanged."""
    run_id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    status: str = "running"  # running | completed | error
    depth: str = "quick"
    model_key: str = ""
    result: dict | None = Field(default=None, sa_column=Column(JSON))
    error: str | None = Field(default=None, sa_column=Column(Text))


class AgentTrace(SQLModel, table=True):
    """Persisted agent timeline: upserted on EACH step transition so the
    frontend can read it mid-run (reload/resume) and replay it later."""
    run_id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    kind: str = "optimize"
    status: str = "running"  # running | completed | error
    depth: str = "quick"
    model_key: str = ""
    steps: list = Field(default_factory=list, sa_column=Column(JSON))  # AgentStepEvent dumps
    summary: dict = Field(default_factory=dict, sa_column=Column(JSON))  # reduce_trace output
