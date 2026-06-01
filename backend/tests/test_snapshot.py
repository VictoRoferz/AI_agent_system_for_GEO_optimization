from app.ingestion.snapshot import MAX_SNAPSHOT_BYTES, sanitize_snapshot, tag_blocks


def test_strips_scripts_and_handlers_and_injects_base():
    html = (
        "<html><head><title>T</title></head>"
        '<body><script>alert(1)</script>'
        '<a href="javascript:evil()" onclick="x()">link</a>'
        "<p>hello</p></body></html>"
    )
    out = sanitize_snapshot(html, "https://example.com/page")
    assert "<script" not in out.lower()
    assert "onclick" not in out.lower()
    assert "javascript:" not in out.lower()
    assert '<base href="https://example.com/page">' in out
    assert "<p>hello</p>" in out


def test_strips_meta_refresh_and_noscript():
    html = (
        '<html><head><meta http-equiv="refresh" content="0;url=/x"></head>'
        "<body><noscript>no js</noscript>ok</body></html>"
    )
    out = sanitize_snapshot(html, "https://example.com")
    assert "http-equiv" not in out.lower()
    assert "noscript" not in out.lower()
    assert "ok" in out


def test_injects_base_when_no_head():
    out = sanitize_snapshot("<html><body>x</body></html>", "https://e.com")
    assert '<base href="https://e.com">' in out


def test_size_capped():
    html = "<html><body>" + ("a" * (MAX_SNAPSHOT_BYTES + 5000)) + "</body></html>"
    out = sanitize_snapshot(html, "https://e.com")
    assert len(out.encode("utf-8")) <= MAX_SNAPSHOT_BYTES


def test_empty_html_returns_empty():
    assert sanitize_snapshot("", "https://e.com") == ""


def test_tag_blocks_anchors_content_and_skips_nav():
    html = (
        "<html><body>"
        "<nav><ul><li>Home menu item here</li><li>Products menu item</li></ul></nav>"
        "<main><h2>Real Article Heading</h2>"
        "<p>This is the article intro paragraph with plenty of text.</p></main>"
        "</body></html>"
    )
    out, blocks = tag_blocks(html)
    texts = [b["text"] for b in blocks]
    # main content tagged; nav items skipped
    assert any("article intro paragraph" in t for t in texts)
    assert any("Real Article Heading" in t for t in texts)
    assert not any("menu item" in t for t in texts)
    # every block has a unique id present in the output html
    ids = [b["id"] for b in blocks]
    assert len(ids) == len(set(ids))
    for gid in ids:
        assert f'data-geo-id="{gid}"' in out


def test_tag_blocks_skips_short_text():
    out, blocks = tag_blocks("<html><body><main><p>Hi</p><p>Long enough paragraph text here</p></main></body></html>")
    assert [b["text"] for b in blocks] == ["Long enough paragraph text here"]
