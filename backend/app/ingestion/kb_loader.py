"""Load the GEO pillar knowledge base into a single cached context block.

The ~20-page KB is small enough to inject in-context. We parse every supported file
in the configured directory once and concatenate into a prompt prefix that the brain
receives on every run (cached on Anthropic via cache_control).

Upgrade path: replace `load_kb_context()` with a vector-store retriever returning
the top-k relevant chunks per query — callers stay unchanged.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.ingestion.doc_parser import parse_path

_SUPPORTED = {".pdf", ".docx", ".doc", ".txt", ".md"}


@lru_cache
def load_kb_context() -> str:
    settings = get_settings()
    kb_dir = settings.kb_path
    if not kb_dir.exists():
        return ""
    parts: list[str] = []
    for path in sorted(kb_dir.iterdir()):
        if path.suffix.lower() not in _SUPPORTED or path.name.startswith("."):
            continue
        try:
            doc = parse_path(path)
        except Exception:
            continue
        if doc.text:
            parts.append(f"### Pillar document: {path.name}\n{doc.text}")
    if not parts:
        return ""
    return (
        "# GEO KNOWLEDGE BASE (authoritative pillars)\n"
        "Use the following internal best-practice material as the primary basis for "
        "scoring and recommendations.\n\n" + "\n\n---\n\n".join(parts)
    )


def kb_is_present() -> bool:
    return bool(load_kb_context())
