from app.analysis.rewrite import _finalize_blocks
from app.analysis.schemas import BlockEdit, PageRewrite, RewriteBlock
from app.storage.repository import apply_edits_to_rewrite


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
