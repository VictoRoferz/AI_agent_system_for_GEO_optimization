"""Fetch a URL and extract GEO-relevant signals.

Strategy: a raw HTTP fetch (what a non-rendering AI crawler sees) plus an optional
Playwright render (what a browser/rendering crawler sees). We diff the two to detect
JS-dependent content, then extract structural + authority + freshness signals.
"""
from __future__ import annotations

import hashlib
import json
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser

from app.analysis.schemas import PageSignals
from app.config import get_settings
from app.storage import repository

USER_AGENT = "Mozilla/5.0 (compatible; GEO-Assistant/0.1; +https://example.com/bot)"
_AI_CRAWLER_UAS = ["GPTBot", "OAI-SearchBot", "PerplexityBot", "Google-Extended", "ClaudeBot"]
_MAX_MAIN_TEXT = 20_000  # chars kept for the brain


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _collect_headings(tree: HTMLParser) -> list[str]:
    out: list[str] = []
    for level in ("h1", "h2", "h3"):
        for node in tree.css(level):
            text = node.text(strip=True)
            if text:
                out.append(f"{level}: {text}")
    return out[:60]


def _parse_jsonld(tree: HTMLParser) -> tuple[bool, list[str], bool, str | None, str | None]:
    """Return (has_jsonld, schema_types, has_author, published, modified)."""
    types: list[str] = []
    has_author = False
    published = modified = None
    nodes = tree.css('script[type="application/ld+json"]')
    for node in nodes:
        raw = node.text() or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for obj in data if isinstance(data, list) else [data]:
            if not isinstance(obj, dict):
                continue
            t = obj.get("@type")
            if isinstance(t, list):
                types.extend(str(x) for x in t)
            elif t:
                types.append(str(t))
            if obj.get("author"):
                has_author = True
            published = published or obj.get("datePublished")
            modified = modified or obj.get("dateModified")
    return bool(nodes), sorted(set(types)), has_author, published, modified


def _meta(tree: HTMLParser, **attrs) -> str | None:
    sel = "meta[" + "][".join(f'{k}="{v}"' for k, v in attrs.items()) + "]"
    node = tree.css_first(sel)
    return node.attributes.get("content") if node else None


def _extract_signals(url: str, status: int, raw_html: str, rendered_html: str | None) -> PageSignals:
    import trafilatura

    html = rendered_html or raw_html
    tree = HTMLParser(html)

    title_node = tree.css_first("title")
    canonical_node = tree.css_first('link[rel="canonical"]')
    html_node = tree.css_first("html")
    has_jsonld, schema_types, has_author, published, modified = _parse_jsonld(tree)

    main_text = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
    raw_main = trafilatura.extract(raw_html, include_comments=False) or ""
    # JS-dependent if the rendered page yields substantially more text than raw HTML.
    js_dependent = bool(rendered_html) and len(main_text) > max(400, len(raw_main) * 1.5)

    author_meta = _meta(tree, name="author")

    return PageSignals(
        final_url=url,
        status_code=status,
        title=title_node.text(strip=True) if title_node else None,
        meta_description=_meta(tree, name="description"),
        canonical=canonical_node.attributes.get("href") if canonical_node else None,
        lang=html_node.attributes.get("lang") if html_node else None,
        headings=_collect_headings(tree),
        word_count=len(main_text.split()),
        has_jsonld=has_jsonld,
        schema_types=schema_types,
        has_author=has_author or bool(author_meta),
        published_date=published or _meta(tree, property="article:published_time"),
        modified_date=modified or _meta(tree, property="article:modified_time"),
        js_dependent=js_dependent,
        main_text=main_text[:_MAX_MAIN_TEXT],
    )


async def _render_with_playwright(url: str) -> str | None:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=USER_AGENT)
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            html = await page.content()
            await browser.close()
            return html
    except Exception:
        return None


async def _check_crawler_files(client: httpx.AsyncClient, url: str) -> dict:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    result = {"robots": False, "llms": False, "blocks_ai": False}
    try:
        r = await client.get(urljoin(base, "/robots.txt"))
        if r.status_code == 200:
            result["robots"] = True
            body = r.text
            result["blocks_ai"] = any(
                ua in body and "Disallow: /" in body for ua in _AI_CRAWLER_UAS
            )
    except httpx.HTTPError:
        pass
    try:
        r = await client.get(urljoin(base, "/llms.txt"))
        result["llms"] = r.status_code == 200
    except httpx.HTTPError:
        pass
    return result


async def fetch_page(url: str, use_cache: bool = True) -> PageSignals:
    settings = get_settings()
    key = _cache_key(url)
    if use_cache:
        cached = await repository.get_cached_signals(key)
        if cached:
            return cached

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30.0
    ) as client:
        resp = await client.get(url)
        raw_html = resp.text
        crawler = await _check_crawler_files(client, str(resp.url))

    rendered = await _render_with_playwright(url) if settings.enable_playwright else None
    signals = _extract_signals(str(resp.url), resp.status_code, raw_html, rendered)
    signals.robots_txt_present = crawler["robots"]
    signals.llms_txt_present = crawler["llms"]
    signals.blocks_ai_crawlers = crawler["blocks_ai"]

    await repository.cache_signals(key, signals)
    return signals
