"""Core Pydantic models shared across ingestion, modes, synthesis, API and storage.

The LLM-facing models (`LLMFinding`, `LLMAnalysis`) are kept lean so they double as
structured-output schemas. The richer `AnalysisResult` is assembled server-side
(adds ids, prioritization buckets, matrix coordinates, metadata).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


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


class ChangeType(str, Enum):
    CONTENT = "content"       # rewrite of reader-facing copy (title, heading, paragraph)
    TECHNICAL = "technical"   # exact code change (JSON-LD, meta tag, markup)


class KBCoverageStatus(str, Enum):
    COVERED = "covered"   # the page already satisfies this knowledge-base factor
    PARTIAL = "partial"   # partially satisfied; room to improve
    GAP = "gap"           # missing / not addressed by the page


class ClaimFlag(str, Enum):
    """Does this factual statement need a study/proof?"""
    GREEN = "green"    # proven on page, or a universally-established fact — no proof needed
    YELLOW = "yellow"  # plausible but unproven on the page — a citation is recommended
    RED = "red"        # sensitive claim with no on-page evidence — proof required and missing


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
class TextBlock(BaseModel):
    """A readable content block in the page snapshot, tagged with a stable id so the
    rewrite can anchor each change to an exact element (data-geo-id in snapshot_html)."""
    id: str   # matches the snapshot's data-geo-id, e.g. "g1"
    tag: str  # "p" | "h2" | "li" | ...
    text: str


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
    snapshot_html: str = ""     # sanitized HTML for the Studio live-preview pane (capped)
    text_blocks: list[TextBlock] = Field(default_factory=list)  # tagged content blocks


class GoalsDocument(BaseModel):
    filename: str
    text: str
    sections: list[str] = Field(default_factory=list)


# -------------------------------------------------------- LLM structured-output models
class ConcreteChange(BaseModel):
    """The actual, usable artifact that makes a recommendation actionable.

    For a CONTENT change the brain supplies the real rewrite (original -> proposed);
    for a TECHNICAL change it supplies the exact code to paste plus step-by-step
    instructions on where/how to apply it.
    """
    change_type: ChangeType
    target: str  # where on the page, e.g. "Title tag", "Intro paragraph", "<head>"
    # CONTENT
    original_text: str | None = None  # quoted from the page ("" / None if net-new)
    proposed_text: str | None = None  # the concrete rewrite
    # TECHNICAL
    code_language: str | None = None  # "html" | "json" | "jsonld"
    code_snippet: str | None = None   # exact code to paste
    instructions: list[str] = Field(default_factory=list)  # step-by-step apply guide


# ------------------------------------------------------- explainability (agent)
class EvidenceRef(BaseModel):
    """A verbatim quote that grounds a finding or a rewrite decision."""
    quote: str
    anchor_id: str | None = None  # data-geo-id of the page block the quote comes from
    source: str = "page"          # page | claim | signal | kb


class Rationale(BaseModel):
    """Structured 'why this change, in this form' attached to findings and rewrite blocks."""
    why: str = ""
    kb_factor_ids: list[str] = Field(default_factory=list)    # canonical factor ids ("f-3")
    kb_factor_names: list[str] = Field(default_factory=list)  # resolved names (== KBCoverageItem.factor)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    queries_targeted: list[str] = Field(default_factory=list)
    expected_effect: str = ""                                 # mechanism -> outcome, one sentence
    recommendation_ids: list[str] = Field(default_factory=list)  # rec-N this implements

    @field_validator("evidence", mode="before")
    @classmethod
    def _coerce_evidence(cls, v):
        # Models sometimes emit bare quote strings; accept them as EvidenceRef quotes.
        if isinstance(v, list):
            return [{"quote": item} if isinstance(item, str) else item for item in v]
        return v


class VerificationIssue(BaseModel):
    """One problem found while verifying a proposed change."""
    kind: str  # unsupported_claim|compliance|meaning_drift|broken_promise|new_number|
    #   rec_unimplemented|compliance_lexicon|flag_quote|missing_rationale
    detail: str
    quote: str = ""              # verbatim substring of the proposed text, where applicable
    block_id: str | None = None


class VerificationOutcome(BaseModel):
    """Self-verification result stamped on a rewrite block by the agent."""
    status: str = "unverified"   # unverified | passed | revised | needs_human
    issues: list[VerificationIssue] = Field(default_factory=list)
    notes: str = ""


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
    change: ConcreteChange | None = None  # the concrete fix (rewrite or code change)
    rationale: Rationale | None = None    # structured why (agent path; None on legacy runs)
    source_agent: str | None = None       # expert id that produced this finding (agent path)


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


class KBCoverageItem(BaseModel):
    """One knowledge-base factor and how the analyzed page measures up against it.

    Surfaced as a checklist so the user can see every KB factor was considered and
    which gaps each recommendation addresses.
    """
    factor: str                                   # the KB factor/pillar name
    status: KBCoverageStatus
    assessment: str                               # one line: how the page does on this factor
    related_rec_ids: list[str] = Field(default_factory=list)  # rec ids that close the gap
    factor_id: str | None = None                  # canonical factor id (agent path)
    related_block_ids: list[str] = Field(default_factory=list)  # rewrite blocks addressing it


class Claim(BaseModel):
    """One factual statement extracted from the page, marked for whether it needs proof.

    Surfaced as a 🟢/🟡/🔴 checklist (and overlaid on the studio) so a regulated-industry
    reviewer can see which statements must be backed by a study/citation.
    """
    text: str                                     # the statement, quoted verbatim from the page
    flag: ClaimFlag
    claim_type: str                               # efficacy|safety|outcome|comparative|
    #   mechanism_disease|indication|dosing|regulatory_status|statistic|company_brand|
    #   economic_cost|testimonial|other
    rationale: str                                # why this flag; what proof is missing & why it matters
    required_evidence: list[str] = Field(default_factory=list)  # proof types needed (empty if green)
    compliant_rewrite: str = ""                   # a compliant version (empty if already compliant)
    anchor_id: str | None = None                  # data-geo-id of the page block this maps to


class ClaimAnalysis(BaseModel):
    """Structured output of the dedicated claim-extraction pass."""
    claims: list[Claim] = Field(default_factory=list)


class LLMAnalysis(BaseModel):
    """Full structured output requested from the brain (mode-agnostic)."""
    executive_summary: str
    overall_score: int = Field(ge=0, le=100)
    engine_readiness: list[EngineReadiness] = Field(default_factory=list)
    alignment: AlignmentAssessment
    findings: list[LLMFinding] = Field(default_factory=list)
    kb_coverage: list[KBCoverageItem] = Field(default_factory=list)


# ---------------------------------------------------------------- assembled result
class Recommendation(LLMFinding):
    id: str
    priority: Priority
    priority_rank: int  # global ordering, 1 = most important
    block_ids: list[str] = Field(default_factory=list)  # rewrite blocks implementing it (agent path)


class AnalysisResult(BaseModel):
    executive_summary: str
    overall_score: int
    engine_readiness: list[EngineReadiness]
    alignment: AlignmentAssessment
    recommendations: list[Recommendation]
    kb_coverage: list[KBCoverageItem] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    compliance_score: int = 0  # deterministic 0-100 evidence/compliance score from claim flags
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


# --------------------------------------------------------------- AI Studio (rewrite)
class ProposedFlag(BaseModel):
    """An inline evidence flag on a span of the PROPOSED/recommended text.

    `quote` is an exact substring of the proposed text (a statement, claim or number)
    so the UI can highlight it; `flag` says whether it needs proof; `note` says what.
    """
    quote: str
    flag: ClaimFlag
    note: str = ""


class ProposedFlagList(BaseModel):
    """Structured output when (re)flagging a single proposed text."""
    flags: list[ProposedFlag] = Field(default_factory=list)


class RewriteBlock(BaseModel):
    """One unit of the proposed page rewrite (original -> proposed) shown in the studio."""
    id: str                                  # "blk-1"
    kind: str                                # "title"|"heading"|"paragraph"|"meta"|"jsonld"
    label: str                               # human label, e.g. "Title tag", "Intro paragraph"
    original: str = ""                       # original text/code ("" if net-new)
    proposed: str = ""                       # the ACTIVE rewrite (= options[selected_option_index])
    options: list[str] = Field(default_factory=list)  # content: 3 distinct-style variants
    selected_option_index: int = 0           # which option is active
    flags: list[ProposedFlag] = Field(default_factory=list)  # inline evidence flags on `proposed`
    changed: bool = False                    # computed server-side (proposed != original)
    is_technical: bool = False               # content vs technical-change block
    change_explanation: str | None = None    # plain-language "why", for changed blocks
    anchor_id: str | None = None             # data-geo-id of the page block this maps to
    rationale: Rationale | None = None       # structured why (agent path)
    verification: VerificationOutcome | None = None  # self-verification stamp (agent path)


class LLMRewrite(BaseModel):
    """Structured rewrite as produced by the brain (server adds run_id/model_key)."""
    summary: str
    content_blocks: list[RewriteBlock] = Field(default_factory=list)
    technical_blocks: list[RewriteBlock] = Field(default_factory=list)


class PageRewrite(BaseModel):
    """The assembled, persisted rewrite for a run."""
    run_id: str
    summary: str
    content_blocks: list[RewriteBlock] = Field(default_factory=list)
    technical_blocks: list[RewriteBlock] = Field(default_factory=list)
    model_key: str
    origin: str = "studio"  # "studio" (manual generate) | "agent" (optimization run)


class BlockEdit(BaseModel):
    """A live edit the chat agent applies to a rewrite block."""
    block_id: str                            # existing block id, or "new"
    label: str | None = None                 # required when block_id == "new"
    is_technical: bool = False               # used when creating a new block
    proposed: str
    change_explanation: str
    options: list[str] = Field(default_factory=list)  # optional fresh 3 variants for the block
    selected_index: int | None = None        # which option to activate (defaults to 0)
    flags: list[ProposedFlag] = Field(default_factory=list)  # inline evidence flags on the new text


class ChatResponse(BaseModel):
    """Structured output for one chat turn in the studio."""
    reply: str
    block_edits: list[BlockEdit] = Field(default_factory=list)
    new_recommendations: list[LLMFinding] = Field(default_factory=list)
