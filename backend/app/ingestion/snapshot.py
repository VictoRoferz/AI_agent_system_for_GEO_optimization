"""Sanitize a fetched page's HTML into a static, safe snapshot.

The snapshot is rendered in the AI Studio left pane inside a sandboxed iframe so the
user sees the page roughly as it looks live, with the agent's to-be-changed text
highlighted. We strip anything active (scripts, event handlers, auto-refresh) and
inject a <base href> so the site's own CSS/images still resolve. The iframe is also
sandboxed (no allow-scripts) as defense in depth.
"""
from __future__ import annotations

import re

# Cap to keep the run JSON blob sane while still fitting whole articles (images + markup).
# A full rendered page is often 1-3 MB; truncating mid-tag blanks the render, so we keep
# this generous and only chop pathological pages.
MAX_SNAPSHOT_BYTES = 4_000_000

_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_NOSCRIPT_RE = re.compile(r"<noscript\b[^>]*>.*?</noscript\s*>", re.IGNORECASE | re.DOTALL)
# <meta http-equiv="refresh" ...> would navigate the iframe away.
_META_REFRESH_RE = re.compile(
    r"<meta\b[^>]*http-equiv\s*=\s*['\"]?refresh['\"]?[^>]*>", re.IGNORECASE
)
# Inline event handlers like onclick="..." / onload='...'.
_ON_HANDLER_RE = re.compile(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)
# javascript: URLs in href/src.
_JS_URL_RE = re.compile(r"(href|src)\s*=\s*(['\"])\s*javascript:[^'\"]*\2", re.IGNORECASE)
_HEAD_RE = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
_HTML_RE = re.compile(r"<html\b[^>]*>", re.IGNORECASE)
# Lazy-loaded images keep the real URL in data-* attributes and only swap it in via JS,
# which we strip — so promote the common lazy attributes to real src/srcset per <img>.
_IMG_TAG_RE = re.compile(r"<img\b[^>]*?/?>", re.IGNORECASE)
_LOADING_LAZY_RE = re.compile(r"\sloading\s*=\s*(['\"])lazy\1", re.IGNORECASE)


def _attr(tag: str, name: str) -> str | None:
    m = re.search(rf'{name}\s*=\s*(["\'])(.*?)\1', tag, re.IGNORECASE)
    return m.group(2) if m else None


def _set_src(tag: str, attr: str, value: str) -> str:
    """Drop any existing `attr` and inject it right after `<img` with the real URL."""
    value = value.replace('"', "%22")
    tag = re.sub(rf'\s{attr}\s*=\s*(["\']).*?\1', "", tag, flags=re.IGNORECASE)
    return re.sub(r"(?i)^<img", f'<img {attr}="{value}"', tag, count=1)


def _fix_img(match: re.Match) -> str:
    tag = match.group(0)
    for cand in ("data-lazy-src", "data-src", "data-original"):
        val = _attr(tag, cand)
        if val:
            tag = _set_src(tag, "src", val)
            break
    for cand in ("data-lazy-srcset", "data-srcset"):
        val = _attr(tag, cand)
        if val:
            tag = _set_src(tag, "srcset", val)
            break
    return _LOADING_LAZY_RE.sub(' loading="eager"', tag)


def sanitize_snapshot(html: str, base_url: str) -> str:
    """Return a static, embeddable version of `html` with a <base href> injected.

    Best-effort, regex-based: strips scripts/noscript/auto-refresh/inline handlers and
    neutralizes javascript: URLs, then ensures a <base href="{base_url}"> so relative
    asset URLs resolve against the original site. Size-capped at MAX_SNAPSHOT_BYTES.
    """
    if not html:
        return ""

    out = _SCRIPT_RE.sub("", html)
    out = _NOSCRIPT_RE.sub("", out)
    out = _META_REFRESH_RE.sub("", out)
    out = _ON_HANDLER_RE.sub("", out)
    out = _JS_URL_RE.sub(r'\1=\2#\2', out)
    out = _IMG_TAG_RE.sub(_fix_img, out)  # promote lazy images so photos render

    base_tag = f'<base href="{base_url}">'
    if "<base" not in out.lower():
        if _HEAD_RE.search(out):
            out = _HEAD_RE.sub(lambda m: m.group(0) + base_tag, out, count=1)
        elif _HTML_RE.search(out):
            out = _HTML_RE.sub(lambda m: m.group(0) + f"<head>{base_tag}</head>", out, count=1)
        else:
            out = f"<head>{base_tag}</head>" + out

    # Cap by encoded size; truncate on a safe boundary if needed.
    encoded = out.encode("utf-8", errors="ignore")
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        out = encoded[:MAX_SNAPSHOT_BYTES].decode("utf-8", errors="ignore")
    return out


# Block-level elements that carry the page's readable content. We tag the outermost
# of these with a stable data-geo-id so the rewrite can anchor changes precisely.
_BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "figcaption")
_MIN_BLOCK_CHARS = 15
_MAX_BLOCKS = 200
_MAX_BLOCK_TEXT = 400
# Chrome/navigation regions whose text isn't the article — don't waste anchors on them.
_SKIP_ANCESTOR_TAGS = {"nav", "header", "footer", "aside", "form"}
_SKIP_ANCESTOR_ROLES = {"navigation", "menu", "menubar", "banner", "contentinfo", "search"}


def tag_blocks(html: str) -> tuple[str, list[dict]]:
    """Assign a stable `data-geo-id` to each outermost content block and return the
    tagged HTML plus a list of {id, tag, text} blocks for anchoring the rewrite.

    Best-effort: on any parse failure the original HTML is returned with no blocks
    (the frontend then falls back to text matching).
    """
    if not html:
        return html, []
    try:
        import lxml.html as LH
    except Exception:
        return html, []
    try:
        tree = LH.document_fromstring(html)
    except Exception:
        return html, []

    body = tree.find("body")
    if body is None:
        return html, []
    # Prefer the main content region if the page marks one.
    root = body.find(".//main")
    if root is None:
        root = body

    blocks: list[dict] = []
    tagged: set = set()
    idx = 0
    for el in root.iter(*_BLOCK_TAGS):
        if len(blocks) >= _MAX_BLOCKS:
            break
        ancestors = list(el.iterancestors())
        # Skip nav/header/footer/etc. chrome and only tag the outermost block.
        if any(
            a.tag in _SKIP_ANCESTOR_TAGS or (a.get("role") or "") in _SKIP_ANCESTOR_ROLES
            for a in ancestors
        ):
            continue
        if any(a in tagged for a in ancestors):
            continue
        text = " ".join((el.text_content() or "").split())
        if len(text) < _MIN_BLOCK_CHARS:
            continue
        idx += 1
        gid = f"g{idx}"
        el.set("data-geo-id", gid)
        tagged.add(el)
        blocks.append({"id": gid, "tag": el.tag, "text": text[:_MAX_BLOCK_TEXT]})

    if not blocks:
        return html, []
    try:
        out = LH.tostring(tree, encoding="unicode")
    except Exception:
        return html, []
    return out, blocks
