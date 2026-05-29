"""SerpApi client — captures Google's AI Overview and its cited source links."""
from __future__ import annotations

import httpx

from app.config import get_settings

_ENDPOINT = "https://serpapi.com/search.json"


def _collect_links(node) -> list[str]:
    """Recursively pull href/link/source_link values out of an AI-overview blob."""
    links: list[str] = []
    if isinstance(node, dict):
        for key in ("link", "source_link", "href"):
            if isinstance(node.get(key), str):
                links.append(node[key])
        for value in node.values():
            links.extend(_collect_links(value))
    elif isinstance(node, list):
        for item in node:
            links.extend(_collect_links(item))
    return links


async def ai_overview_sources(query: str) -> list[str]:
    """Return the source URLs cited in Google's AI Overview for a query.

    Returns [] if there is no AI Overview for the query.
    Raises RuntimeError if no API key is configured.
    """
    settings = get_settings()
    if not settings.serpapi_api_key:
        raise RuntimeError("SERPAPI_API_KEY not configured")
    params = {"engine": "google", "q": query, "api_key": settings.serpapi_api_key}
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.get(_ENDPOINT, params=params)
        resp.raise_for_status()
        data = resp.json()

    overview = data.get("ai_overview")
    if not overview:
        return []
    # References are usually under ai_overview.references; fall back to deep link scan.
    refs = overview.get("references") or []
    links = [r.get("link") for r in refs if isinstance(r, dict) and r.get("link")]
    if not links:
        links = _collect_links(overview)
    return [link for link in dict.fromkeys(links) if link]
