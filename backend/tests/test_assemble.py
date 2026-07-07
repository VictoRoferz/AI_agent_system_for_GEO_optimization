"""Deterministic page assembly — anchored replacement, head changes, safety fallbacks."""
from app.agent.assemble import assemble_page, classify_technical
from app.analysis.schemas import PageRewrite, Rationale, RewriteBlock, VerificationOutcome

SNAPSHOT = """<html><head><base href="https://x.test/"><title>Old title</title>
<meta name="description" content="old desc"></head>
<body><main>
<h1 data-geo-id="g1">Old heading</h1>
<p data-geo-id="g2">Old paragraph with <strong>markup</strong>.</p>
<p data-geo-id="g3">Kept paragraph.</p>
</main></body></html>"""


def _block(bid, anchor, proposed, *, kind="paragraph", changed=True, status="passed", **kw):
    return RewriteBlock(
        id=bid, kind=kind, label=f"{kind} {bid}", original="x", proposed=proposed,
        changed=changed, anchor_id=anchor,
        verification=VerificationOutcome(status=status) if changed else None, **kw,
    )


def _rewrite(content=None, technical=None) -> PageRewrite:
    return PageRewrite(
        run_id="r", summary="s", model_key="gpt", origin="agent",
        content_blocks=content or [], technical_blocks=technical or [],
    )


def test_anchored_text_replacement_and_title_sync():
    rw = _rewrite(content=[
        _block("blk-1", "g1", "New heading", kind="title"),
        _block("blk-2", "g2", "New paragraph."),
    ])
    out = assemble_page(SNAPSHOT, rw)
    assert "New heading" in out.html and "New paragraph." in out.html
    assert "Old paragraph" not in out.html
    assert "<title>New heading</title>" in out.html
    assert "Kept paragraph." in out.html
    assert out.applied_block_ids == ["blk-1", "blk-2"]


def test_needs_human_falls_back_to_original_under_verified():
    rw = _rewrite(content=[_block("blk-1", "g2", "Risky text", status="needs_human")])
    out = assemble_page(SNAPSHOT, rw, include="verified")
    assert "Risky text" not in out.html
    assert out.skipped_block_ids == ["blk-1"]
    out_all = assemble_page(SNAPSHOT, rw, include="all")
    assert "Risky text" in out_all.html


def test_jsonld_inserted_and_invalid_json_skipped():
    good = _block("blk-t1", None, '{"@context": "https://schema.org", "@type": "MedicalWebPage"}',
                  kind="jsonld")
    bad = _block("blk-t2", None, "{not json", kind="jsonld")
    out = assemble_page(SNAPSHOT, _rewrite(technical=[good, bad]))
    assert 'application/ld+json' in out.html and "MedicalWebPage" in out.html
    assert any("not valid JSON" in n for n in out.not_applied)
    assert "blk-t1" in out.applied_block_ids and "blk-t2" not in out.applied_block_ids


def test_meta_canonical_and_new_section():
    rw = _rewrite(
        content=[_block("blk-9", None, "Answer-first summary text.", kind="paragraph",
                        rationale=Rationale(why="net new"))],
        technical=[
            _block("blk-t1", None, '<meta name="description" content="new desc">', kind="meta"),
            _block("blk-t2", None, '<link rel="canonical" href="https://x.test/page">', kind="canonical"),
        ],
    )
    out = assemble_page(SNAPSHOT, rw)
    assert 'content="new desc"' in out.html
    assert 'rel="canonical"' in out.html and "https://x.test/page" in out.html
    assert 'data-geo-new="blk-9"' in out.html and "Answer-first summary text." in out.html


def test_deployable_strips_base_and_geo_attrs():
    rw = _rewrite(content=[_block("blk-1", "g1", "New heading")])
    out = assemble_page(SNAPSHOT, rw, deployable=True)
    assert "<base" not in out.html
    assert "data-geo-id" not in out.html


def test_missing_anchor_goes_to_manifest_and_empty_snapshot_degrades():
    rw = _rewrite(content=[_block("blk-1", "g404", "text")])
    out = assemble_page(SNAPSHOT, rw)
    assert any("g404" in n for n in out.not_applied)
    empty = assemble_page("", rw)
    assert empty.html == "" and empty.not_applied


def test_classify_technical():
    assert classify_technical(_block("b", None, '{"@context": "https://schema.org"}', kind="x")) == "jsonld"
    assert classify_technical(_block("b", None, '<meta name="description" content="d">', kind="x")) == "meta_description"
    assert classify_technical(_block("b", None, "<title>T</title>", kind="x")) == "title"
    assert classify_technical(_block("b", None, '<link rel="canonical" href="h">', kind="x")) == "canonical"
    assert classify_technical(_block("b", None, "User-agent: GPTBot\nAllow: /", kind="x")) == "other"
