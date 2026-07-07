"""Pydantic models specific to the optimization agent.

These wrap / extend the shared analysis schemas: the agent plans, audits per KB
factor, rewrites per block batch, verifies, and assembles an OptimizationResult
persisted alongside (never inside) the immutable analysis Run.result.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.analysis.schemas import (
    Claim,
    EngineReadiness,
    EvidenceRef,
    KBCoverageItem,
    LLMFinding,
    Rationale,
    Recommendation,
    RewriteBlock,
    VerificationIssue,
)

# ------------------------------------------------------------------ KB factors
FACTOR_CATEGORIES = (
    "content_structure",
    "evidence_authority",
    "technical_schema",
    "entity_brand",
    "freshness",
    "crawl_access",
    "compliance",
    "off_page",
)


class KBFactor(BaseModel):
    """One canonical, independently checkable GEO lever derived from the KB."""
    id: str = ""  # "f-1"... server-assigned, stable per KB hash
    name: str
    description: str = ""
    category: str = "content_structure"  # one of FACTOR_CATEGORIES
    criteria: list[str] = Field(default_factory=list)  # 2-6 binary checks per factor
    importance: int = Field(default=3, ge=1, le=5)
    applies_to: str = "page"  # page | site
    source_doc: str = ""


class LLMFactorList(BaseModel):
    """Structured output of the factor-extraction call."""
    factors: list[KBFactor] = Field(default_factory=list)


class KBFactorSet(BaseModel):
    """The cached canonical factor list, snapshotted into every OptimizationResult."""
    kb_hash: str
    extracted_at: str = ""
    model_key: str = ""
    factors: list[KBFactor] = Field(default_factory=list)


# ------------------------------------------------------------------------ plan
class BlockPlanItem(BaseModel):
    anchor_id: str
    action: str = "rewrite"  # rewrite | keep | merge | remove
    reason: str = ""
    priority: int = Field(default=3, ge=1, le=5)


class NewSectionPlan(BaseModel):
    label: str
    placement_hint: str = "end"
    reason: str = ""


class OptimizationPlan(BaseModel):
    strategy_summary: str = ""
    style_brief: str = ""  # voice/terminology brief ALL rewrite batches follow
    block_plan: list[BlockPlanItem] = Field(default_factory=list)
    new_sections: list[NewSectionPlan] = Field(default_factory=list)
    technical_plan: list[str] = Field(default_factory=list)
    source: str = "llm"  # "llm" | "heuristic"


# ----------------------------------------------------------------------- audit
class AuditFinding(LLMFinding):
    """A finding from a factor audit — rationale is REQUIRED on the agent path."""
    rationale: Rationale


class FactorAudit(BaseModel):
    factor_id: str
    status: str = "gap"  # covered | partial | gap | error
    severity: int = Field(default=3, ge=1, le=5)
    assessment: str = ""
    evidence_quotes: list[EvidenceRef] = Field(default_factory=list)
    findings: list[AuditFinding] = Field(default_factory=list)


class FactorAuditBatch(BaseModel):
    """Structured output of one expert's audit call."""
    audits: list[FactorAudit] = Field(default_factory=list)


# --------------------------------------------------------------------- rewrite
class RewriteBatch(BaseModel):
    """Structured output of one rewrite / technical / revision call."""
    blocks: list[RewriteBlock] = Field(default_factory=list)


# ---------------------------------------------------------------------- verify
class BlockVerdict(BaseModel):
    block_id: str
    verdict: str = "pass"  # pass | revise | fail
    issues: list[VerificationIssue] = Field(default_factory=list)
    suggested_fix: str | None = None


class VerificationBatch(BaseModel):
    """Structured output of one skeptic-verifier call."""
    verdicts: list[BlockVerdict] = Field(default_factory=list)


class VerificationReport(BaseModel):
    passed: int = 0
    revised: int = 0
    needs_human: int = 0
    issues_total: int = 0
    by_kind: dict[str, int] = Field(default_factory=dict)


class QueryJudgement(BaseModel):
    query: str
    before_would_cite: bool = False
    after_would_cite: bool = False
    reasoning: str = ""


class CitationJudgement(BaseModel):
    """Before/after citation-readiness prediction (explicitly PREDICTED)."""
    before: list[EngineReadiness] = Field(default_factory=list)
    after: list[EngineReadiness] = Field(default_factory=list)
    per_query: list[QueryJudgement] = Field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------- result
class ScoreCard(BaseModel):
    overall_score: int | None = None
    heuristic_baseline: int = 0
    compliance_score: int | None = None
    engine_readiness: list[EngineReadiness] = Field(default_factory=list)


class ExpertProfile(BaseModel):
    id: str
    name: str
    role: str = ""


class OptimizationResult(BaseModel):
    """Everything the agent produced except the PageRewrite (that lives in StudioState)."""
    run_id: str
    depth: str
    model_key: str
    experts: list[ExpertProfile] = Field(default_factory=list)
    factor_set: KBFactorSet
    plan: OptimizationPlan = Field(default_factory=OptimizationPlan)
    audits: list[FactorAudit] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    kb_coverage: list[KBCoverageItem] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    verification: VerificationReport = Field(default_factory=VerificationReport)
    citation_judgement: CitationJudgement | None = None
    before: ScoreCard = Field(default_factory=ScoreCard)
    after: ScoreCard = Field(default_factory=ScoreCard)
    claims_addressed: int = 0
    stats: dict = Field(default_factory=dict)  # llm_calls, wall_ms, blocks_changed, ...
    notes: list[str] = Field(default_factory=list)
