from app.analysis.rewrite import _finalize_blocks, _resolve_anchors
from app.analysis.schemas import BlockEdit, PageRewrite, RewriteBlock, TextBlock
from app.storage.repository import apply_edits_to_rewrite


def test_resolve_anchors_backfills_missing_anchor():
    tbs = [
        TextBlock(id="g1", tag="li", text="Menu item home"),
        TextBlock(id="g7", tag="p", text="Cochlear implants can restore binaural hearing for SSD patients."),
    ]
    matched = RewriteBlock(id="blk-1", kind="paragraph", label="Intro",
                           original="Cochlear implants can restore binaural hearing for SSD patients.",
                           proposed="x")
    netnew = RewriteBlock(id="blk-2", kind="paragraph", label="New", original="", proposed="y")
    _resolve_anchors([matched, netnew], tbs)
    assert matched.anchor_id == "g7"   # backfilled by text match
    assert netnew.anchor_id is None    # net-new stays unanchored


def test_resolve_anchors_keeps_existing_anchor():
    tbs = [TextBlock(id="g3", tag="p", text="Some page text here that is long enough")]
    blk = RewriteBlock(id="blk-1", kind="paragraph", label="x", original="anything",
                       proposed="z", anchor_id="g9")
    _resolve_anchors([blk], tbs)
    assert blk.anchor_id == "g9"  # not overwritten


def test_finalize_sets_proposed_to_first_option_for_content():
    b = RewriteBlock(id="x", kind="paragraph", label="Intro", original="old",
                     options=["v1", "v2", "v3"])
    _finalize_blocks([b], 1, technical=False)
    assert b.id == "blk-1"
    assert b.proposed == "v1"
    assert b.selected_option_index == 0
    assert b.options == ["v1", "v2", "v3"]
    assert b.changed is True


def test_finalize_clears_options_for_technical():
    b = RewriteBlock(id="x", kind="jsonld", label="Schema", original="",
                     proposed="<code/>", options=["a", "b"])
    _finalize_blocks([b], 5, technical=True)
    assert b.options == []
    assert b.is_technical is True


def test_apply_edit_with_options_switches_proposed():
    block = RewriteBlock(id="blk-1", kind="paragraph", label="Intro", original="old",
                         proposed="v1", options=["v1", "v2", "v3"], selected_option_index=0)
    rw = PageRewrite(run_id="r", summary="", content_blocks=[block], model_key="gpt")
    edit = BlockEdit(block_id="blk-1", proposed="ignored", change_explanation="why",
                     options=["n1", "n2", "n3"], selected_index=1)
    out = apply_edits_to_rewrite(rw, [edit])
    b = out.content_blocks[0]
    assert b.options == ["n1", "n2", "n3"]
    assert b.selected_option_index == 1
    assert b.proposed == "n2"
