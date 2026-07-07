"""KB factor materialization — pure helpers (hashing, ids, normalization, rendering)."""
from app.agent.factors import (
    assign_factor_ids,
    factor_names_by_id,
    kb_hash,
    normalize_factors,
    render_factor_context,
)
from app.agent.schemas import KBFactor, KBFactorSet


def _factor(name: str, category: str = "content_structure", **kw) -> KBFactor:
    return KBFactor(name=name, category=category, **kw)


def test_kb_hash_stable_and_content_sensitive():
    assert kb_hash("pillar text") == kb_hash("pillar text")
    assert kb_hash("pillar text") != kb_hash("pillar text v2")
    assert kb_hash("") == kb_hash("")


def test_assign_factor_ids_deterministic_order():
    factors = [
        _factor("Zebra factor", "technical_schema"),
        _factor("Answer-first intro", "content_structure"),
        _factor("Author bio", "evidence_authority"),
    ]
    ids1 = assign_factor_ids(factors)
    ids2 = assign_factor_ids(list(reversed(factors)))  # input order must not matter
    assert [f.id for f in ids1] == ["f-1", "f-2", "f-3"]
    assert [(f.id, f.name) for f in ids1] == [(f.id, f.name) for f in ids2]
    # sorted by (category, name): content_structure < evidence_authority < technical_schema
    assert ids1[0].name == "Answer-first intro"
    assert ids1[2].name == "Zebra factor"


def test_normalize_factors_coerces_unknown_category_and_drops_empty_names():
    factors = [
        _factor("Valid", "technical_schema"),
        KBFactor(name="Weird category", category="seo_magic"),
        KBFactor(name="   ", category="content_structure"),
    ]
    out = normalize_factors(factors)
    assert len(out) == 2
    assert out[0].category == "technical_schema"
    assert out[1].category == "content_structure"  # coerced


def test_render_factor_context_lists_every_factor_with_id():
    fs = KBFactorSet(
        kb_hash="x",
        factors=assign_factor_ids(
            [
                _factor("Answer-first intro", criteria=["Intro answers the query in 2 sentences"]),
                _factor("JSON-LD present", "technical_schema"),
            ]
        ),
    )
    ctx = render_factor_context(fs)
    assert "# CANONICAL GEO FACTORS" in ctx
    assert "f-1" in ctx and "f-2" in ctx
    assert "Answer-first intro" in ctx
    assert "Intro answers the query in 2 sentences" in ctx


def test_factor_names_by_id():
    fs = KBFactorSet(kb_hash="x", factors=assign_factor_ids([_factor("A"), _factor("B")]))
    names = factor_names_by_id(fs)
    assert names == {"f-1": "A", "f-2": "B"}
