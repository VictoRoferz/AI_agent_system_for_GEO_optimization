"""Depth/cost control: what each depth runs, and the pure partitioning helpers.

quick  ≈ 7-8 LLM calls  — heuristic plan, merged-pair audits, 1 option per block.
full   ≈ 15-18 LLM calls — LLM plan, per-expert audits, 3 options, verification loop.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agent.prompts import EXPERTS, QUICK_AUDIT_PAIRS
from app.agent.schemas import KBFactor
from app.analysis.schemas import TextBlock


@dataclass(frozen=True)
class DepthConfig:
    key: str
    plan_llm: bool             # LLM planner vs pure heuristic plan
    audit_group_size: int      # max factors per audit call (oversized experts get chunked)
    concurrency: int           # shared semaphore for fan-out calls
    rewrite_batch_blocks: int  # max blocks per rewrite call
    rewrite_batch_chars: int   # max original chars per rewrite call
    options_per_block: int     # 3 keeps the studio's conservative/balanced/punchy tabs
    net_new_sections: bool
    skeptic_mode: str          # "single" (one compact call) | "batched" (per rewrite batch)
    revision_loop: bool
    recheck_claims_after: bool
    max_llm_calls: int         # hard cap; optional steps are skipped past it


DEPTHS: dict[str, DepthConfig] = {
    "quick": DepthConfig(
        key="quick",
        plan_llm=False,
        audit_group_size=12,
        concurrency=2,
        rewrite_batch_blocks=15,   # sized so 1-option output fits the token ceiling
        rewrite_batch_chars=6_000,
        options_per_block=1,
        net_new_sections=False,
        skeptic_mode="single",
        revision_loop=False,
        recheck_claims_after=False,
        max_llm_calls=18,  # long pages need ~9 rewrite batches + audits + verify lenses
    ),
    "full": DepthConfig(
        key="full",
        plan_llm=True,
        audit_group_size=6,
        concurrency=4,
        rewrite_batch_blocks=12,
        rewrite_batch_chars=6_000,
        options_per_block=3,
        net_new_sections=True,
        skeptic_mode="batched",
        revision_loop=True,
        recheck_claims_after=True,
        max_llm_calls=40,
    ),
}


def _chunk(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)] if items else []


def expert_audit_partitions(
    factors: list[KBFactor], depth: DepthConfig
) -> list[tuple[list[str], list[KBFactor]]]:
    """Audit calls as (expert_ids, factors) pairs.

    full  → one call per expert over its owned categories (chunked if oversized);
    quick → the two merged expert pairs. Factors in categories nobody owns fall to
    the content strategist (defensive — the registry covers every category).
    """
    groups: list[tuple[list[str], tuple[str, ...]]] = []
    if depth.key == "quick":
        for pair in QUICK_AUDIT_PAIRS:
            cats: tuple[str, ...] = ()
            for eid in pair:
                cats += EXPERTS[eid].categories
            groups.append((list(pair), cats))
    else:
        for eid, expert in EXPERTS.items():
            if expert.categories:
                groups.append(([eid], expert.categories))

    owned = {c for _, cats in groups for c in cats}
    partitions: list[tuple[list[str], list[KBFactor]]] = []
    for expert_ids, cats in groups:
        mine = [f for f in factors if f.category in cats]
        if expert_ids[0] == "content" or "content" in expert_ids:
            mine += [f for f in factors if f.category not in owned]
        for chunk in _chunk(mine, depth.audit_group_size):
            partitions.append((expert_ids, chunk))
    return partitions


def partition_blocks(
    blocks: list[TextBlock], max_blocks: int, max_chars: int
) -> list[list[TextBlock]]:
    """Pack text blocks into rewrite batches in document order, capped by count and size.
    A single block longer than max_chars still ships (alone) — never dropped."""
    batches: list[list[TextBlock]] = []
    current: list[TextBlock] = []
    chars = 0
    for b in blocks:
        size = len(b.text or "")
        if current and (len(current) >= max_blocks or chars + size > max_chars):
            batches.append(current)
            current, chars = [], 0
        current.append(b)
        chars += size
    if current:
        batches.append(current)
    return batches


def estimate_calls(depth: DepthConfig, n_factors: int, n_blocks: int) -> int:
    """Rough LLM-call count for this depth (planning aid + budget sanity)."""
    audit = max(1, -(-n_factors // depth.audit_group_size))  # ceil, ≥1 group per pair/expert
    rewrite = max(1, -(-n_blocks // depth.rewrite_batch_blocks))
    calls = audit + rewrite + 1  # + technical
    if depth.plan_llm:
        calls += 1
    if depth.net_new_sections:
        calls += 1
    calls += 1 if depth.skeptic_mode == "single" else rewrite  # skeptic
    if depth.revision_loop:
        calls += 1
    calls += 1  # citation judge
    return calls
