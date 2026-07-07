"""Assemble phase (deterministic, no LLM): apply the verified rewrite into the
page snapshot to produce a deployable HTML file, plus the markdown change package.

Applying is anchor-driven (data-geo-id) — the same ids the studio panes use — so
what you preview is what you export. Blocks flagged needs_human keep their
original text under include="verified" (the conservative default).
"""
from __future__ import annotations

import json
import re

from lxml import html as lxml_html
from pydantic import BaseModel, Field

from app.agent.schemas import OptimizationResult
from app.analysis.schemas import PageRewrite, RewriteBlock


class AssembledPage(BaseModel):
    html: str = ""
    applied_block_ids: list[str] = Field(default_factory=list)
    skipped_block_ids: list[str] = Field(default_factory=list)  # needs_human under "verified"
    not_applied: list[str] = Field(default_factory=list)  # manifest of manual steps


# ------------------------------------------------------------------ classification
def classify_technical(block: RewriteBlock) -> str:
    """jsonld | meta_description | title | canonical | other — by kind, then sniffing."""
    kind = (block.kind or "").lower()
    label = (block.label or "").lower()
    text = (block.proposed or "").strip()
    if kind == "jsonld" or "json-ld" in label or "ld+json" in text:
        return "jsonld"
    if text.startswith("{") and '"@context"' in text:
        return "jsonld"
    if kind == "meta" or "meta description" in label or 'name="description"' in text:
        return "meta_description"
    if kind == "title" or label == "title" or "title tag" in label or text.startswith("<title"):
        return "title"
    if kind == "canonical" or "canonical" in label or 'rel="canonical"' in text:
        return "canonical"
    return "other"


def _extract_jsonld(text: str) -> str | None:
    """The JSON payload from either a bare object or a <script> wrapper; None if invalid."""
    m = re.search(r"<script[^>]*>(.*?)</script>", text, re.DOTALL | re.IGNORECASE)
    payload = (m.group(1) if m else text).strip()
    try:
        json.loads(payload)
    except json.JSONDecodeError:
        return None
    return payload


def _extract_attr(text: str, attr: str) -> str | None:
    m = re.search(rf'{attr}\s*=\s*"([^"]*)"', text) or re.search(rf"{attr}\s*=\s*'([^']*)'", text)
    return m.group(1) if m else None


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


# ----------------------------------------------------------------------- assembly
def _should_apply(block: RewriteBlock, include: str) -> bool:
    if not block.changed:
        return False
    if include == "all":
        return True
    status = block.verification.status if block.verification else "unverified"
    return status != "needs_human"


def _set_text(el, text: str) -> None:
    """Replace an element's content with plain text, keeping attributes and tail."""
    for child in list(el):
        el.remove(child)
    el.text = text


def assemble_page(
    snapshot_html: str,
    rewrite: PageRewrite,
    include: str = "verified",
    deployable: bool = False,
) -> AssembledPage:
    """Pure. Apply content blocks at their anchors + technical changes into <head>."""
    out = AssembledPage()
    if not (snapshot_html or "").strip():
        out.not_applied.append("No page snapshot captured — re-run the analysis first.")
        return out
    doc = lxml_html.fromstring(snapshot_html)
    head = doc.find("head")
    body = doc.find("body")

    # Content blocks: replace text at the anchored element.
    new_sections: list[RewriteBlock] = []
    for b in rewrite.content_blocks:
        if not _should_apply(b, include):
            if b.changed:
                out.skipped_block_ids.append(b.id)
            continue
        if not b.anchor_id:
            new_sections.append(b)
            continue
        els = doc.xpath(f'//*[@data-geo-id="{b.anchor_id}"]')
        if not els:
            out.not_applied.append(f"{b.id}: anchor {b.anchor_id} not found in the snapshot.")
            continue
        _set_text(els[0], b.proposed)
        out.applied_block_ids.append(b.id)
        if b.kind == "title" and head is not None:
            t = head.find("title")
            if t is not None:
                t.text = b.proposed

    # Net-new sections: append to <main> (or body).
    target = doc.find(".//main")
    if target is None:
        target = body
    for b in new_sections:
        if target is None:
            out.not_applied.append(f"{b.id}: no <body> to append the new section to.")
            continue
        section = lxml_html.Element("section")
        section.set("data-geo-new", b.id)
        h = lxml_html.Element("h2")
        h.text = b.label
        p = lxml_html.Element("p")
        p.text = b.proposed
        section.append(h)
        section.append(p)
        target.append(section)
        out.applied_block_ids.append(b.id)

    # Technical changes into <head>.
    for b in rewrite.technical_blocks:
        if not _should_apply(b, include):
            if b.changed:
                out.skipped_block_ids.append(b.id)
            continue
        kind = classify_technical(b)
        if head is None:
            out.not_applied.append(f"{b.id} ({b.label}): snapshot has no <head>.")
            continue
        if kind == "jsonld":
            payload = _extract_jsonld(b.proposed)
            if payload is None:
                out.not_applied.append(f"{b.id} ({b.label}): JSON-LD is not valid JSON — apply manually.")
                continue
            script = lxml_html.Element("script", type="application/ld+json")
            script.text = payload
            head.append(script)
        elif kind == "meta_description":
            content = _extract_attr(b.proposed, "content") or _strip_tags(b.proposed)
            metas = doc.xpath('//head/meta[@name="description"]')
            if metas:
                metas[0].set("content", content)
            else:
                meta = lxml_html.Element("meta", name="description", content=content)
                head.append(meta)
        elif kind == "title":
            text = _strip_tags(b.proposed)
            t = head.find("title")
            if t is not None:
                t.text = text
            else:
                t = lxml_html.Element("title")
                t.text = text
                head.append(t)
        elif kind == "canonical":
            href = _extract_attr(b.proposed, "href") or _strip_tags(b.proposed)
            links = doc.xpath('//head/link[@rel="canonical"]')
            if links:
                links[0].set("href", href)
            else:
                link = lxml_html.Element("link", rel="canonical", href=href)
                head.append(link)
        else:
            out.not_applied.append(
                f"{b.id} ({b.label}): applies outside the page (robots.txt/llms.txt/server) — "
                "see the change package."
            )
            continue
        out.applied_block_ids.append(b.id)

    if deployable:
        for base in doc.xpath("//base"):
            base.getparent().remove(base)
        for el in doc.xpath("//*[@data-geo-id]"):
            del el.attrib["data-geo-id"]
        for el in doc.xpath("//*[@data-geo-new]"):
            del el.attrib["data-geo-new"]

    out.html = "<!doctype html>\n" + lxml_html.tostring(doc, encoding="unicode")
    return out


# ------------------------------------------------------------------ change package
def render_change_package(
    optimization: OptimizationResult,
    rewrite: PageRewrite,
    url: str,
    not_applied: list[str] | None = None,
) -> str:
    """Pure. Markdown package: every change + why + verification + code + scores."""
    lines: list[str] = [
        "# Optimized page — change package",
        "",
        f"**URL:** {url}  ",
        f"**Depth:** {optimization.depth} · **Model:** {optimization.model_key} · "
        f"**LLM calls:** {optimization.stats.get('llm_calls', '?')}",
        "",
    ]

    j = optimization.citation_judgement
    if j and j.after:
        lines += ["## Predicted citation-readiness (before → after)", ""]
        lines += ["| Engine | Before | After | Δ |", "| --- | --- | --- | --- |"]
        before_by = {er.engine.value: er.score for er in j.before}
        for er in j.after:
            b = before_by.get(er.engine.value)
            delta = f"{er.score - b:+d}" if b is not None else "—"
            lines.append(f"| {er.engine.value} | {b if b is not None else '—'} | {er.score} | {delta} |")
        if j.per_query:
            lines += ["", "| Query | Cited before? | Cited after? |", "| --- | --- | --- |"]
            for q in j.per_query:
                lines.append(
                    f"| {q.query} | {'yes' if q.before_would_cite else 'no'} | "
                    f"{'yes' if q.after_would_cite else 'no'} |"
                )
        if j.summary:
            lines += ["", f"> {j.summary}"]
        lines.append("")

    v = optimization.verification
    lines += [
        "## Self-verification",
        f"- ✓ {v.passed} blocks verified · ⚠ {v.revised} revised after review · "
        f"✗ {v.needs_human} flagged for human review",
        f"- {optimization.claims_addressed} claim risk(s) from the original page addressed",
        "",
    ]

    changed = [b for b in rewrite.content_blocks if b.changed]
    lines += [f"## Content changes ({len(changed)})", ""]
    for b in changed:
        status = b.verification.status if b.verification else "unverified"
        lines += [f"### {b.label} ({b.id}) — {status}", ""]
        if b.original:
            lines += ["**Before:**", "", f"> {b.original}", ""]
        lines += ["**After:**", "", f"> {b.proposed}", ""]
        r = b.rationale
        why = (r.why if r else "") or b.change_explanation or ""
        if why:
            lines.append(f"**Why:** {why}")
        if r:
            if r.kb_factor_names:
                lines.append(f"**KB factors:** {', '.join(r.kb_factor_names)}")
            if r.queries_targeted:
                lines.append(f"**Targets queries:** {', '.join(r.queries_targeted)}")
            if r.expected_effect:
                lines.append(f"**Expected effect:** {r.expected_effect}")
        lines.append("")

    tech = [b for b in rewrite.technical_blocks if b.changed or not b.original]
    if tech:
        lines += [f"## Technical changes ({len(tech)})", ""]
        for b in tech:
            lines += [f"### {b.label} ({b.id})", "", "```html", b.proposed, "```", ""]
            why = (b.rationale.why if b.rationale else "") or b.change_explanation or ""
            if why:
                lines += [f"**Why:** {why}", ""]

    if not_applied:
        lines += ["## Not applied automatically (manual steps)", ""]
        lines += [f"- {n}" for n in not_applied]
        lines.append("")

    if optimization.kb_coverage:
        lines += ["## KB factor coverage", "", "| Factor | Status | Assessment |", "| --- | --- | --- |"]
        for c in optimization.kb_coverage:
            lines.append(f"| {c.factor} | {c.status.value} | {c.assessment} |")
        lines.append("")

    reds = [c for c in optimization.claims if c.flag.value in ("red", "yellow")]
    if reds:
        lines += ["## Claim risks on the original page", "",
                  "| Flag | Claim | What would substantiate it |", "| --- | --- | --- |"]
        for c in reds:
            ev = "; ".join(c.required_evidence) or "—"
            lines.append(f"| {c.flag.value} | {c.text} | {ev} |")
        lines.append("")

    return "\n".join(lines)
