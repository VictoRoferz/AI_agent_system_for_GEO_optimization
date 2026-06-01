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
