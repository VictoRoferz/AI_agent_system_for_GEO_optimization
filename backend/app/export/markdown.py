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
        lines.append("")

    if result.notes:
        lines += ["## Notes", *[f"- {n}" for n in result.notes]]

    return "\n".join(lines)
