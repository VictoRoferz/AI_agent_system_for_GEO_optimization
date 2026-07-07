"""KB factor materialization: derive a canonical, enumerated factor list from the KB.

Today the KB is one prose blob and "factors" only exist as free text the synthesis
brain invents per run. The agent needs a stable, id-addressable checklist, so we
extract it once per KB content hash (LLM call), cache it (DB row + in-process memo),
and snapshot it into every OptimizationResult so old runs stay interpretable after
KB edits.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.agent.prompts import FACTOR_EXTRACTOR
from app.agent.schemas import FACTOR_CATEGORIES, KBFactor, KBFactorSet, LLMFactorList
from app.core.llm import complete_structured
from app.storage import repository

# Sanity bounds: fewer factors means the extractor collapsed the KB; more means it
# shredded it into non-actionable fragments.
MIN_FACTORS = 8
MAX_FACTORS = 60

_memo: dict[str, KBFactorSet] = {}


def kb_hash(kb_context: str) -> str:
    return hashlib.sha256((kb_context or "").encode("utf-8")).hexdigest()


def normalize_factors(factors: list[KBFactor]) -> list[KBFactor]:
    """Coerce unknown categories to content_structure and drop empty names."""
    out: list[KBFactor] = []
    for f in factors:
        if not (f.name or "").strip():
            continue
        category = f.category if f.category in FACTOR_CATEGORIES else "content_structure"
        out.append(f.model_copy(update={"category": category, "name": f.name.strip()}))
    return out


def assign_factor_ids(factors: list[KBFactor]) -> list[KBFactor]:
    """Deterministic ids: sort by (category, name), assign f-1..f-N. Stable per KB hash."""
    ordered = sorted(factors, key=lambda f: (f.category, f.name.lower()))
    return [f.model_copy(update={"id": f"f-{i}"}) for i, f in enumerate(ordered, start=1)]


def render_factor_context(fs: KBFactorSet) -> str:
    """Compact enumerated list appended to the KB blob as the run-wide cache prefix."""
    lines = ["# CANONICAL GEO FACTORS", "Audit and reference factors by these ids."]
    for f in fs.factors:
        crit = " Checks: " + "; ".join(f.criteria) if f.criteria else ""
        lines.append(
            f"- {f.id} [{f.category}] {f.name} (importance {f.importance}/5): {f.description}{crit}"
        )
    return "\n".join(lines)


def factor_names_by_id(fs: KBFactorSet) -> dict[str, str]:
    return {f.id: f.name for f in fs.factors}


async def _extract(kb_context: str, model_key: str | None) -> list[KBFactor]:
    corrective = ""
    factors: list[KBFactor] = []
    for _ in range(2):
        result = await complete_structured(
            system=FACTOR_EXTRACTOR + corrective,
            user="Extract the canonical factor list from the knowledge base above.",
            schema=LLMFactorList,
            model_key=model_key,
            cache_prefix=kb_context or None,
            temperature=0.1,
            max_tokens=6000,
        )
        factors = normalize_factors(result.factors)
        if MIN_FACTORS <= len(factors) <= MAX_FACTORS:
            return factors
        corrective = (
            f"\n\nYour previous attempt returned {len(factors)} factors, outside the "
            f"expected {MIN_FACTORS}-{MAX_FACTORS} range. Re-derive the checklist at the "
            "right granularity: one independently checkable lever per factor."
        )
    raise RuntimeError(
        f"KB factor extraction returned {len(factors)} factors "
        f"(expected {MIN_FACTORS}-{MAX_FACTORS})"
    )


async def get_factor_set(
    kb_context: str, model_key: str | None = None, refresh: bool = False
) -> KBFactorSet:
    """Canonical factor set for this KB content — memo → DB cache → LLM extraction."""
    if not (kb_context or "").strip():
        raise ValueError(
            "Knowledge base is empty — add pillar documents to Knowledge_base/ and restart "
            "the backend."
        )
    h = kb_hash(kb_context)
    if not refresh:
        if h in _memo:
            return _memo[h]
        cached = await repository.get_factor_set(h)
        if cached is not None:
            _memo[h] = cached
            return cached
    extracted = await _extract(kb_context, model_key)
    fs = KBFactorSet(
        kb_hash=h,
        extracted_at=datetime.now(timezone.utc).isoformat(),
        model_key=model_key or "",
        factors=assign_factor_ids(extracted),
    )
    await repository.save_factor_set(fs)
    _memo[h] = fs
    return fs
