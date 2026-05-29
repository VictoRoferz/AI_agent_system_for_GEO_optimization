"""Turn extracted PageSignals into a human-readable GEO factor briefing for the brain.

This is deterministic, content-agnostic structuring — the brain does the judgement.
A lightweight heuristic baseline score is also produced for transparency/debugging.
"""
from __future__ import annotations

from app.analysis.schemas import PageSignals


def summarize_signals(s: PageSignals) -> str:
    """A compact, factual briefing of the page's GEO-relevant structure."""
    lines = [
        "## Extracted page signals",
        f"- Final URL: {s.final_url} (HTTP {s.status_code})",
        f"- Title: {s.title or '(missing)'}",
        f"- Meta description: {s.meta_description or '(missing)'}",
        f"- Canonical: {s.canonical or '(none)'}",
        f"- Language: {s.lang or '(unset)'}",
        f"- Word count (main content): {s.word_count}",
        f"- Headings ({len(s.headings)}): {', '.join(s.headings[:15]) or '(none)'}",
        f"- Structured data (JSON-LD): {'yes' if s.has_jsonld else 'no'}"
        + (f"; types: {', '.join(s.schema_types)}" if s.schema_types else ""),
        f"- Author present: {'yes' if s.has_author else 'no'}",
        f"- Published: {s.published_date or '(unknown)'}; Modified: {s.modified_date or '(unknown)'}",
        f"- robots.txt present: {'yes' if s.robots_txt_present else 'no'}; "
        f"llms.txt present: {'yes' if s.llms_txt_present else 'no'}",
        f"- Blocks known AI crawlers (robots.txt): {'YES' if s.blocks_ai_crawlers else 'no'}",
        f"- Content JS-dependent (hidden from non-rendering crawlers): "
        f"{'YES' if s.js_dependent else 'no'}",
        "",
        "## Main content (extracted, may be truncated)",
        s.main_text or "(no main content extracted)",
    ]
    return "\n".join(lines)


def heuristic_baseline(s: PageSignals) -> int:
    """A rough 0-100 citability baseline from objective signals (not authoritative)."""
    score = 50
    if s.title:
        score += 5
    if s.meta_description:
        score += 5
    if s.has_jsonld:
        score += 10
    if s.has_author:
        score += 5
    if s.modified_date or s.published_date:
        score += 5
    if s.word_count >= 600:
        score += 10
    if len(s.headings) >= 3:
        score += 5
    if s.llms_txt_present:
        score += 5
    if s.js_dependent:
        score -= 15
    if s.blocks_ai_crawlers:
        score -= 30
    return max(0, min(100, score))
