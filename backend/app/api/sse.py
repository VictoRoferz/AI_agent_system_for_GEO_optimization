"""Shared SSE plumbing: event formatting + keepalive heartbeat for long streams."""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def with_heartbeat(stream: AsyncIterator[str], every_s: float = 15.0) -> AsyncIterator[str]:
    """Pass chunks through, emitting an SSE comment when the stream is quiet so
    proxies don't kill long-running LLM calls. Comment chunks are ignored by the
    frontend parser (no event:/data: pair)."""
    it = stream.__aiter__()
    while True:
        nxt = asyncio.ensure_future(it.__anext__())
        while True:
            try:
                chunk = await asyncio.wait_for(asyncio.shield(nxt), timeout=every_s)
                yield chunk
                break
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
            except StopAsyncIteration:
                return
