"""Shared types for analysis modes."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.analysis.schemas import (
    AnalysisRequest,
    EngineReadiness,
    GoalsDocument,
    PageSignals,
)


@dataclass
class ModeContext:
    request: AnalysisRequest
    page: PageSignals
    goals: GoalsDocument | None
    kb_context: str


@dataclass
class ModeOutput:
    """What a mode contributes to synthesis."""
    # Free-text evidence injected into the brain's synthesis prompt.
    evidence_text: str = ""
    # Engine readiness values the mode *observed* directly (real data / live / simulated).
    # Synthesis prefers these over brain-predicted values.
    observed_engines: list[EngineReadiness] = field(default_factory=list)
    # Operator-facing notes (e.g. "Peec: domain not tracked", "Perplexity key missing").
    notes: list[str] = field(default_factory=list)
    # How the brain should frame this mode in the executive summary.
    mode_framing: str = ""


ModeHandler = Callable[[ModeContext], Awaitable[ModeOutput]]
