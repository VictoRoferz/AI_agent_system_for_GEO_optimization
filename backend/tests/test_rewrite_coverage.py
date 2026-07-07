"""validate_batch_coverage — full-page coverage as a deterministic invariant."""
from app.agent.rewriter import validate_batch_coverage
from app.analysis.rewrite import _finalize_blocks
from app.analysis.schemas import Rationale, RewriteBlock, TextBlock


def _tb(i: int, text: str = "original text here", tag: str = "p") -> TextBlock:
    return TextBlock(id=f"g{i}", tag=tag, text=text)


def _rb(anchor: str | None, proposed: str, original: str = "original text here") -> RewriteBlock:
    return RewriteBlock(
        id="", kind="paragraph", label="b", original=original, proposed=proposed,
        options=[proposed], anchor_id=anchor, rationale=Rationale(why="w"),
    )


def test_missing_block_backfilled_as_keep_as_is():
    inputs = [_tb(1), _tb(2)]
    out = validate_batch_coverage(inputs, [_rb("g1", "improved text")])
    assert [b.anchor_id for b in out] == ["g1", "g2"]
    assert out[1].proposed == out[1].original == inputs[1].text
    assert "kept the original" in out[1].rationale.why.lower()


def test_duplicate_anchor_first_wins_and_unknown_dropped():
    inputs = [_tb(1)]
    out = validate_batch_coverage(
        inputs, [_rb("g1", "first"), _rb("g1", "second"), _rb("g99", "ghost")]
    )
    assert len(out) == 1
    assert out[0].proposed == "first"


def test_original_mismatch_corrected_to_page_text():
    inputs = [_tb(1, text="the REAL page text")]
    out = validate_batch_coverage(inputs, [_rb("g1", "new", original="hallucinated original")])
    assert out[0].original == "the REAL page text"


def test_empty_proposed_falls_back_to_original():
    inputs = [_tb(1)]
    out = validate_batch_coverage(inputs, [_rb("g1", "   ")])
    assert out[0].proposed == inputs[0].text


def test_heading_tag_maps_to_heading_kind_and_finalize_assigns_ids():
    inputs = [_tb(1, tag="h2"), _tb(2)]
    out = validate_batch_coverage(inputs, [])
    assert out[0].kind == "heading"
    nxt = _finalize_blocks(out, 1, technical=False)
    assert nxt == 3
    assert [b.id for b in out] == ["blk-1", "blk-2"]
    assert all(b.changed is False for b in out)  # keep-as-is backfill is not a change
