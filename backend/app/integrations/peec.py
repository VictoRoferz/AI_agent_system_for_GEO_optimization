"""Peec AI client — pull real brand/domain visibility & citation metrics.

Peec's exact REST schema may vary by account; this client targets a conventional
`/v1/domains/{domain}/report` shape and degrades gracefully (returns None) when the
key is missing, the domain is untracked, or the schema differs. The Peec mode then
falls back to brain prediction with a clear operator note.
"""
from __future__ import annotations

import httpx

from app.config import get_settings


async def domain_report(domain: str) -> dict | None:
    settings = get_settings()
    if not settings.peec_api_key:
        return None
    url = f"{settings.peec_base_url.rstrip('/')}/v1/domains/{domain}/report"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                url, headers={"Authorization": f"Bearer {settings.peec_api_key}"}
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None
