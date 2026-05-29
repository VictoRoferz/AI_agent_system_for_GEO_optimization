"""Core Pydantic models shared across ingestion, modes, synthesis, API and storage.

The LLM-facing models (`LLMFinding`, `LLMAnalysis`) are kept lean so they double as
structured-output schemas. The richer `AnalysisResult` is assembled server-side
(adds ids, prioritization buckets, matrix coordinates, metadata).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- enums
class AnalysisMode(str, Enum):
    PEEC = "peec"               # mode 1: real Peec AI data
    SIMULATION = "simulation"   # mode 2: brain role-plays the engine
    LIVE = "live"               # mode 3: query real engines
    GEO_FACTORS = "geo_factors" # mode 4: GEO factors + knowledge base


class TargetEngine(str, Enum):
    CHATGPT = "chatgpt"
    AI_OVERVIEWS = "ai_overviews"
    PERPLEXITY = "perplexity"
    GEMINI = "gemini"


class Priority(str, Enum):
    P0 = "P0"  # critical / do first
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"  # nice to have


class Effort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalStatus(str, Enum):
    OBSERVED = "observed"     # measured against a real engine / real data
    PREDICTED = "predicted"   # estimated by the brain


# ------------------------------------------------------------------------- request
class AnalysisRequest(BaseModel):
    url: str
    queries: list[str] = Field(default_factory=list)
    mode: AnalysisMode = AnalysisMode.GEO_FACTORS
    target_engines: list[TargetEngine] = Field(
        default_factory=lambda: [TargetEngine.CHATGPT, TargetEngine.AI_OVERVIEWS]
    )
    model_key: str | None = None
    # strategic-goals doc is uploaded as a file; its parsed text is attached separately.


# ----------------------------------------------------------------------- ingestion
class PageSignals(BaseModel):
    """GEO-relevant signals extracted from the fetched page."""
    final_url: str
    status_code: int | None = None
    title: str | None = None
    meta_description: str | None = None
    canonical: str | None = None
    lang: str | None = None
    headings: list[str] = Field(default_factory=list)        # e.g. "h1: Title"
    word_count: int = 0
    has_jsonld: bool = False
    schema_types: list[str] = Field(default_factory=list)    # schema.org @type values
    has_author: bool = False
    published_date: str | None = None
    modified_date: str | None = None
    robots_txt_present: bool = False
    llms_txt_present: bool = False
    blocks_ai_crawlers: bool = False
    js_dependent: bool = False  # significant content only present after JS render
    main_text: str = ""         # extracted readable content (may be truncated downstream)


class GoalsDocument(BaseModel):
    filename: str
    text: str
    sections: list[str] = Field(default_factory=list)


# -------------------------------------------------------- LLM structured-output models
class LLMFinding(BaseModel):
    """A single recommendation as produced by the brain."""
    title: str
    description: str
    why_it_matters: str
    expected_impact: str
    impact_score: int = Field(ge=1, le=5, description="1=minor, 5=transformational")
    effort: Effort
    confidence: int = Field(ge=1, le=5, description="1=speculative, 5=certain")
    evidence: list[str] = Field(default_factory=list)
    target_engine: TargetEngine | None = None


class EngineReadiness(BaseModel):
    engine: TargetEngine
    score: int = Field(ge=0, le=100, description="citation-readiness 0-100")
    status: SignalStatus
    rationale: str


class AlignmentAssessment(BaseModel):
    goal_alignment_score: int = Field(ge=0, le=100)
    goal_alignment_summary: str
    query_coverage_score: int = Field(ge=0, le=100)
    query_coverage_summary: str
    gaps: list[str] = Field(default_factory=list)


class LLMAnalysis(BaseModel):
    """Full structured output requested from the brain (mode-agnostic)."""
    executive_summary: str
    overall_score: int = Field(ge=0, le=100)
    engine_readiness: list[EngineReadiness] = Field(default_factory=list)
    alignment: AlignmentAssessment
    findings: list[LLMFinding] = Field(default_factory=list)


# ---------------------------------------------------------------- assembled result
class Recommendation(LLMFinding):
    id: str
    priority: Priority
    priority_rank: int  # global ordering, 1 = most important


class AnalysisResult(BaseModel):
    executive_summary: str
    overall_score: int
    engine_readiness: list[EngineReadiness]
    alignment: AlignmentAssessment
    recommendations: list[Recommendation]
    # context / metadata
    url: str
    queries: list[str]
    mode: AnalysisMode
    model_key: str
    target_engines: list[TargetEngine]
    page_signals: PageSignals | None = None
    notes: list[str] = Field(default_factory=list)  # e.g. "Peec: domain not tracked"


# ------------------------------------------------------------------- SSE progress
class ProgressEvent(BaseModel):
    step: str
    message: str
    pct: int = Field(ge=0, le=100)
