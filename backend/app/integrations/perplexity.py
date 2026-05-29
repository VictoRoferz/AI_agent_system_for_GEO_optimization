"""Perplexity API client — returns the source URLs Perplexity cited for a query."""
from __future__ import annotations

import httpx

from app.config import get_settings

_ENDPOINT = "https://api.perplexity.ai/chat/completions"


async def cited_sources(query: str, model: str = "sonar") -> list[str]:
    """Run a query against Perplexity and return the list of cited source URLs.

    Raises RuntimeError if no API key is configured.
    """
    settings = get_settings()
    if not settings.perplexity_api_key:
        raise RuntimeError("PERPLEXITY_API_KEY not configured")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": query}],
        "return_citations": True,
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {settings.perplexity_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    # Perplexity returns citations either top-level or under search_results.
    citations = data.get("citations") or []
    if not citations:
        citations = [r.get("url") for r in data.get("search_results", []) if r.get("url")]
    return [c for c in citations if c]
