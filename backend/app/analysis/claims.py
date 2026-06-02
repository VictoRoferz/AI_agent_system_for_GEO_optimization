"""Claim & evidence check — extract every factual statement on the page and mark, for
each, whether it needs a study/proof (🟢/🟡/🔴), given the sensitivity of pharma / medtech /
healthcare content.

This is a dedicated pass (run concurrently with synthesis). Judgment is page-only: the brain
decides from on-page evidence + its medical knowledge. The deterministic `compliance_score`
rolls the flags into a single 0-100 number, kept separate from the GEO citation score.
"""
from __future__ import annotations

from app.analysis.schemas import (
    AnalysisRequest,
    Claim,
    ClaimAnalysis,
    ClaimFlag,
    GoalsDocument,
    PageSignals,
)
from app.core.llm import complete_structured

# Medical claim types weigh heaviest — an unproven efficacy/safety claim is a regulatory risk.
_MEDICAL_TYPES = {
    "efficacy",
    "safety",
    "outcome",
    "comparative",
    "mechanism_disease",
    "indication",
    "dosing",
    "regulatory_status",
}

_SYSTEM = """You are a strict medical-regulatory EVIDENCE REVIEWER for pharma / medtech / \
biotech / healthcare content. Your single job: read the page and inventory EVERY material \
factual statement, then mark — for each — whether it needs a study or proof, given how \
sensitive the claim is in this regulated industry.

PROOF-REQUIRED STANCE (apply to every statement):
- Treat EVERY factual statement as a claim that must be proven. The burden of proof is on the \
page. Do not accept or endorse a statement just because it sounds reasonable.
- A statement is GREEN only if EITHER the page itself cites/links adequate evidence (a \
peer-reviewed study, RCT, systematic review/meta-analysis, regulatory approval (FDA/EMA/CE/MDR), \
an authoritative institution (WHO/CDC/NIH/NICE), or a clinical guideline) OR it is a \
universally-established, non-promotional fact (e.g. "the cochlea is part of the inner ear").
- YELLOW = plausible but unproven on the page: likely true yet uncited, vague attribution, a \
weak/non-authoritative source, or mildly promotional wording. Fix by adding a citation or softening.
- RED = proof required and MISSING: a sensitive medical efficacy / safety / superiority / \
outcome claim with no on-page evidence; an absolute or comparative claim ("best", "#1", "cure", \
"guaranteed", "superior to X"); an off-label implication; or a statement that contradicts \
established evidence. An uncited medical efficacy/safety/outcome claim defaults to RED, not YELLOW.

For EACH claim return:
  * `text` — the statement quoted VERBATIM from the page (concise; the specific sentence/phrase).
  * `flag` — "green" | "yellow" | "red".
  * `claim_type` — one of: efficacy, safety, outcome, comparative, mechanism_disease, indication, \
dosing, regulatory_status, statistic, company_brand, economic_cost, testimonial, other.
  * `rationale` — one or two sentences: exactly what proof is missing (or present) and why it \
matters in this regulated industry.
  * `required_evidence` — the TYPES of proof that would substantiate it (e.g. "peer-reviewed \
study", "randomized controlled trial", "systematic review", "FDA/EMA/CE approval", "clinical \
guideline", "authoritative institution source"). Leave EMPTY only for green claims.
  * `compliant_rewrite` — a compliant version of the statement (e.g. softened, or noting evidence \
is needed). Leave empty if the statement is already fully compliant.
  * `anchor_id` — the id of the page block (from the "Page content blocks" list) the statement \
lives in, e.g. "g7". Leave null if it has no matching block.

HARD RULES:
- NEVER fabricate citations, DOIs, URLs, study names, author names, or statistics. If you are not \
certain a source exists, do not name it — describe the TYPE of evidence needed instead.
- Be exhaustive across the whole page: product/efficacy/safety claims, disease statements, \
statistics, comparative & superiority language, regulatory status, company/brand and economic \
claims, and testimonials. Do not invent claims that aren't on the page."""


def _signals_block(page: PageSignals) -> str:
    headings = "\n".join(f"  - {h}" for h in page.headings[:30]) or "  (none)"
    return (
        f"## Page\n"
        f"URL: {page.final_url}\n"
        f"Title: {page.title or '(none)'}\n"
        f"Headings:\n{headings}\n\n"
        f"## Main text (extracted)\n{page.main_text[:14000]}"
    )


def _page_blocks(page: PageSignals) -> str:
    """Enumerate the tagged content blocks so claims can anchor to a data-geo-id."""
    if not page.text_blocks:
        return "## Page content blocks\n(none captured — leave anchor_id null)"
    lines = [f"- {b.id} [{b.tag}]: {b.text}" for b in page.text_blocks]
    return "## Page content blocks (anchor each claim to one of these ids)\n" + "\n".join(lines)


def _goals_block(goals: GoalsDocument | None) -> str:
    if not goals or not goals.text:
        return ""
    return f"\n\n## Strategic goals (context only)\n{goals.text[:2000]}"


async def extract_claims(
    request: AnalysisRequest,
    page: PageSignals,
    goals: GoalsDocument | None,
    kb_context: str,
) -> list[Claim]:
    """Run the dedicated claim-extraction pass and return the flagged claims."""
    user = f"{_signals_block(page)}\n\n{_page_blocks(page)}{_goals_block(goals)}"
    result = await complete_structured(
        system=_SYSTEM,
        user=user,
        schema=ClaimAnalysis,
        model_key=request.model_key,
        cache_prefix=kb_context or None,
        max_tokens=8000,
    )
    return result.claims


def compliance_score(claims: list[Claim]) -> int:
    """Deterministic 0-100 evidence/compliance score from the claim flags.

    Start at 100 and subtract weighted penalties — an unproven *medical* claim costs far more
    than a soft marketing phrase. Kept deterministic (like prioritization) for transparency.
    """
    if not claims:
        return 100
    penalty = 0
    for c in claims:
        medical = c.claim_type in _MEDICAL_TYPES
        if c.flag == ClaimFlag.RED:
            penalty += 18 if medical else 8
        elif c.flag == ClaimFlag.YELLOW:
            penalty += 4 if medical else 2
    return max(0, min(100, 100 - penalty))
