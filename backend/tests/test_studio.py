"""Tests for the concrete-change recommendations and the AI Studio rewrite/chat logic."""
from app.analysis.prioritization import prioritize
from app.analysis.rewrite import _finalize_blocks, _norm
from app.analysis.schemas import (
    BlockEdit,
    ChangeType,
    ConcreteChange,
    Effort,
    LLMFinding,
    PageRewrite,
    RewriteBlock,
)
from app.storage.repository import _suggestions, apply_edits_to_rewrite


def _finding(title="t", change=None):
    return LLMFinding(
        title=title,
        description="d",
        why_it_matters="w",
        expected_impact="i",
        impact_score=4,
        effort=Effort.LOW,
        confidence=4,
        change=change,
    )


# ----------------------------------------------------------------- concrete change
def test_change_defaults_to_none_and_is_optional():
    f = _finding()
    assert f.change is None


def test_concrete_change_carries_through_prioritization():
    change = ConcreteChange(
        change_type=ChangeType.CONTENT,
        target="Title tag",
        original_text="Old",
        proposed_text="New, query-front-loaded title",
    )
    recs = prioritize([_finding(change=change)])
    assert recs[0].change is not None
    assert recs[0].change.change_type == ChangeType.CONTENT
    assert recs[0].change.proposed_text == "New, query-front-loaded title"


def test_technical_change_fields():
    change = ConcreteChange(
        change_type=ChangeType.TECHNICAL,
        target="<head>",
        code_language="jsonld",
        code_snippet='{"@context":"https://schema.org"}',
        instructions=["Paste into <head>", "Validate with Rich Results test"],
    )
    f = _finding(change=change)
    assert f.change.code_snippet.startswith("{")
    assert len(f.change.instructions) == 2


# --------------------------------------------------------------- rewrite block flags
def test_norm_collapses_whitespace():
    assert _norm("  a\n b   c ") == "a b c"


def test_finalize_blocks_assigns_ids_and_changed_flag():
    blocks = [
        RewriteBlock(id="x", kind="title", label="Title", original="Same", proposed="Same  "),
        RewriteBlock(id="y", kind="paragraph", label="Intro", original="Old", proposed="New"),
    ]
    nxt = _finalize_blocks(blocks, start=1, technical=False)
    assert [b.id for b in blocks] == ["blk-1", "blk-2"]
    assert blocks[0].changed is False  # whitespace-only diff => unchanged
    assert blocks[1].changed is True
    assert all(b.is_technical is False for b in blocks)
    assert nxt == 3


# ----------------------------------------------------------------- block edits (pure)
def _rewrite():
    return PageRewrite(
        run_id="r1",
        summary="s",
        content_blocks=[
            RewriteBlock(id="blk-1", kind="title", label="Title", original="A", proposed="A"),
        ],
        technical_blocks=[],
        model_key="gpt",
    )


def test_apply_edit_updates_existing_block():
    rw = apply_edits_to_rewrite(
        _rewrite(),
        [BlockEdit(block_id="blk-1", proposed="A much better title", change_explanation="clearer")],
    )
    blk = rw.content_blocks[0]
    assert blk.proposed == "A much better title"
    assert blk.changed is True
    assert blk.change_explanation == "clearer"


def test_apply_edit_adds_new_block():
    rw = apply_edits_to_rewrite(
        _rewrite(),
        [
            BlockEdit(
                block_id="new",
                label="FAQ section",
                is_technical=False,
                proposed="Q: ...? A: ...",
                change_explanation="adds answerable content",
            )
        ],
    )
    assert len(rw.content_blocks) == 2
    assert rw.content_blocks[1].id == "blk-2"
    assert rw.content_blocks[1].changed is True


# --------------------------------------------------------- chat-proposed suggestions
def test_suggestions_reid_with_sug_prefix():
    recs = _suggestions([_finding("a"), _finding("b")])
    assert [r.id for r in recs] == ["sug-1", "sug-2"]
