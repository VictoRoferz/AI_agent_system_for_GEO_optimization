"""Budget/partitioning helpers — expert audit partitions, block batching, estimates."""
from app.agent.budget import DEPTHS, estimate_calls, expert_audit_partitions, partition_blocks
from app.agent.schemas import KBFactor
from app.analysis.schemas import TextBlock


def _factor(name: str, category: str) -> KBFactor:
    return KBFactor(id=f"f-{name}", name=name, category=category)


def _blocks(sizes: list[int]) -> list[TextBlock]:
    return [TextBlock(id=f"g{i+1}", tag="p", text="x" * n) for i, n in enumerate(sizes)]


FACTORS = [
    _factor("jsonld", "technical_schema"),
    _factor("crawler", "crawl_access"),
    _factor("intro", "content_structure"),
    _factor("fresh", "freshness"),
    _factor("cites", "evidence_authority"),
    _factor("claims", "compliance"),
    _factor("entity", "entity_brand"),
    _factor("links", "off_page"),
]


def test_full_partitions_one_call_per_expert():
    parts = expert_audit_partitions(FACTORS, DEPTHS["full"])
    experts = [p[0] for p in parts]
    assert [e[0] for e in experts] == ["technical", "content", "compliance", "brand"]
    # every factor appears exactly once across partitions
    seen = [f.id for _, fs in parts for f in fs]
    assert sorted(seen) == sorted(f.id for f in FACTORS)


def test_quick_partitions_merge_expert_pairs():
    parts = expert_audit_partitions(FACTORS, DEPTHS["quick"])
    assert len(parts) == 2
    assert parts[0][0] == ["technical", "brand"]
    assert parts[1][0] == ["content", "compliance"]
    seen = [f.id for _, fs in parts for f in fs]
    assert sorted(seen) == sorted(f.id for f in FACTORS)


def test_oversized_expert_gets_chunked():
    many = [_factor(f"t{i}", "technical_schema") for i in range(15)]
    parts = expert_audit_partitions(many, DEPTHS["full"])  # group size 6
    tech_parts = [fs for e, fs in parts if e == ["technical"]]
    assert [len(fs) for fs in tech_parts] == [6, 6, 3]


def test_partition_blocks_respects_both_caps_and_order():
    blocks = _blocks([100, 100, 100, 100])
    assert [len(b) for b in partition_blocks(blocks, max_blocks=2, max_chars=10_000)] == [2, 2]
    batches = partition_blocks(blocks, max_blocks=10, max_chars=250)
    assert [len(b) for b in batches] == [2, 2]
    flat = [b.id for batch in batches for b in batch]
    assert flat == ["g1", "g2", "g3", "g4"]  # document order preserved


def test_partition_blocks_oversized_single_block_still_ships():
    blocks = _blocks([50, 9999, 50])
    batches = partition_blocks(blocks, max_blocks=10, max_chars=100)
    assert [[b.id for b in batch] for batch in batches] == [["g1"], ["g2"], ["g3"]]
    assert partition_blocks([], 5, 100) == []


def test_estimate_calls_orders_depths_sensibly():
    quick = estimate_calls(DEPTHS["quick"], n_factors=24, n_blocks=40)
    full = estimate_calls(DEPTHS["full"], n_factors=24, n_blocks=40)
    assert quick < full
    assert quick <= DEPTHS["quick"].max_llm_calls
