"""Render an AnalysisResult to a Markdown report."""
from __future__ import annotations

from app.analysis.schemas import AnalysisResult


def render_markdown(result: AnalysisResult) -> str:
    lines: list[str] = [
        "# GEO Analysis Report",
        "",
        f"**URL:** {result.url}  ",
        f"**Mode:** {result.mode.value} · **Model:** {result.model_key} · "
        f"**Engines:** {', '.join(e.value for e in result.target_engines)}  ",
        f"**Overall GEO score:** {result.overall_score}/100",
        "",
        "## Executive summary",
        result.executive_summary,
        "",
        "## Citation readiness by engine",
        "",
        "| Engine | Score | Status | Rationale |",
        "| --- | --- | --- | --- |",
    ]
    for er in result.engine_readiness:
        lines.append(
            f"| {er.engine.value} | {er.score}/100 | {er.status.value} | {er.rationale} |"
        )

    a = result.alignment
    lines += [
        "",
        "## Strategic alignment",
        f"- **Goal alignment:** {a.goal_alignment_score}/100 — {a.goal_alignment_summary}",
        f"- **Query coverage:** {a.query_coverage_score}/100 — {a.query_coverage_summary}",
    ]
    if a.gaps:
        lines.append("- **Gaps:**")
        lines += [f"  - {g}" for g in a.gaps]

    lines += ["", "## Prioritized recommendations", ""]
    for rec in result.recommendations:
        lines += [
            f"### {rec.priority_rank}. [{rec.priority.value}] {rec.title}",
            rec.description,
            "",
            f"- **Why it matters:** {rec.why_it_matters}",
            f"- **Expected impact:** {rec.expected_impact}",
            f"- **Impact:** {rec.impact_score}/5 · **Effort:** {rec.effort.value} · "
            f"**Confidence:** {rec.confidence}/5",
        ]
        if rec.evidence:
            lines.append("- **Evidence:** " + "; ".join(rec.evidence))
        ch = rec.change
        if ch is not None:
            if ch.proposed_text:
                lines.append(f"- **Proposed copy ({ch.target}):** {ch.proposed_text}")
            if ch.code_snippet:
                lines += [f"- **Code to apply ({ch.target}):**", "", "```", ch.code_snippet, "```"]
        lines.append("")

    if result.kb_coverage:
        lines += [
            "## Knowledge-base coverage",
            "",
            "| Factor | Status | Assessment |",
            "| --- | --- | --- |",
        ]
        for item in result.kb_coverage:
            lines.append(f"| {item.factor} | {item.status.value} | {item.assessment} |")
        lines.append("")

    if result.claims:
        lines += [
            f"## Claim & evidence check (compliance score {result.compliance_score}/100)",
            "",
            "| Flag | Claim | Type | Needs |",
            "| --- | --- | --- | --- |",
        ]
        for c in result.claims:
            needs = "; ".join(c.required_evidence) or "—"
            lines.append(f"| {c.flag.value} | {c.text} | {c.claim_type} | {needs} |")
        lines.append("")

    if result.notes:
        lines += ["## Notes", *[f"- {n}" for n in result.notes]]

    return "\n".join(lines)
