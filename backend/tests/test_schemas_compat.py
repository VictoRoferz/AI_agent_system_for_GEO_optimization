"""Backward compatibility + prompt single-sourcing.

1. Persisted JSON from BEFORE the agent fields existed must still validate.
2. The shared compliance / concrete-change blocks must appear verbatim in every
   prompt that claims to enforce them (analysis, studio and agent paths).
"""
from app.agent import prompts as agent_prompts
from app.analysis import rewrite as rewrite_mod
from app.analysis import synthesis as synthesis_mod
from app.analysis.schemas import (
    KBCoverageItem,
    PageRewrite,
    Recommendation,
    RewriteBlock,
)
from app.agent.schemas import KBFactor
from app.core.prompt_blocks import (
    COMPLIANCE_BLOCK,
    COMPLIANCE_BLOCK_REWRITE,
    CONCRETE_CHANGE_BLOCK,
)


# ------------------------------------------------- old persisted shapes still load
def test_old_rewrite_block_json_still_validates():
    old = {
        "id": "blk-1",
        "kind": "paragraph",
        "label": "Intro",
        "original": "a",
        "proposed": "b",
        "options": ["b"],
        "selected_option_index": 0,
        "flags": [],
        "changed": True,
        "is_technical": False,
        "change_explanation": "why",
        "anchor_id": "g1",
    }
    block = RewriteBlock.model_validate(old)
    assert block.rationale is None
    assert block.verification is None


def test_old_recommendation_json_still_validates():
    old = {
        "id": "rec-1",
        "title": "t",
        "description": "d",
        "why_it_matters": "w",
        "expected_impact": "e",
        "impact_score": 4,
        "effort": "low",
        "confidence": 4,
        "evidence": [],
        "target_engine": None,
        "change": None,
        "priority": "P1",
        "priority_rank": 1,
    }
    rec = Recommendation.model_validate(old)
    assert rec.rationale is None
    assert rec.source_agent is None
    assert rec.block_ids == []


def test_old_kb_coverage_and_page_rewrite_still_validate():
    item = KBCoverageItem.model_validate(
        {"factor": "F", "status": "gap", "assessment": "a", "related_rec_ids": ["rec-1"]}
    )
    assert item.factor_id is None and item.related_block_ids == []
    pr = PageRewrite.model_validate(
        {"run_id": "r", "summary": "s", "content_blocks": [], "technical_blocks": [], "model_key": "gpt"}
    )
    assert pr.origin == "studio"


# ------------------------------------------------------- prompt single-sourcing
def test_pipeline_prompts_embed_shared_blocks_verbatim():
    assert COMPLIANCE_BLOCK in synthesis_mod._SYSTEM
    assert CONCRETE_CHANGE_BLOCK in synthesis_mod._SYSTEM
    assert COMPLIANCE_BLOCK_REWRITE in rewrite_mod._REWRITE_SYSTEM


def test_agent_prompts_embed_compliance_verbatim():
    factors = [KBFactor(id="f-1", name="Answer-first intro")]
    assert COMPLIANCE_BLOCK in agent_prompts.PLANNER
    auditor = agent_prompts.auditor_system(["technical"], factors)
    assert COMPLIANCE_BLOCK in auditor
    assert CONCRETE_CHANGE_BLOCK in auditor
    assert COMPLIANCE_BLOCK_REWRITE in agent_prompts.rewriter_system(3)
    assert COMPLIANCE_BLOCK_REWRITE in agent_prompts.rewriter_system(1)
    assert COMPLIANCE_BLOCK_REWRITE in agent_prompts.TECHNICAL_REWRITER
    assert COMPLIANCE_BLOCK_REWRITE in agent_prompts.NEW_SECTIONS_WRITER
    assert COMPLIANCE_BLOCK_REWRITE in agent_prompts.REVISER
    assert COMPLIANCE_BLOCK in agent_prompts.SKEPTIC
    assert COMPLIANCE_BLOCK in agent_prompts.COMPLIANCE_VERIFIER


def test_expert_registry_covers_all_audit_categories():
    from app.agent.schemas import FACTOR_CATEGORIES

    owned = [c for e in agent_prompts.EXPERTS.values() for c in e.categories]
    assert sorted(owned) == sorted(FACTOR_CATEGORIES)  # each category owned exactly once
    for a, b in agent_prompts.QUICK_AUDIT_PAIRS:
        assert a in agent_prompts.EXPERTS and b in agent_prompts.EXPERTS


def test_auditor_prompt_confines_to_given_factors():
    factors = [
        KBFactor(id="f-3", name="JSON-LD present", category="technical_schema"),
        KBFactor(id="f-7", name="Crawlable by GPTBot", category="crawl_access"),
    ]
    prompt = agent_prompts.auditor_system(["technical"], factors)
    assert "f-3" in prompt and "f-7" in prompt
    assert "Technical GEO Engineer" in prompt
