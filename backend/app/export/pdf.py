"""Render an AnalysisResult to a consulting-styled PDF via Playwright (Chromium print).

Self-contained: builds a styled HTML document and prints it to PDF, so it does not
depend on the frontend being up.
"""
from __future__ import annotations

import html

from app.analysis.schemas import AnalysisResult

_PRIORITY_COLOR = {"P0": "#b91c1c", "P1": "#ea580c", "P2": "#ca8a04", "P3": "#0f766e"}


def _esc(text: str) -> str:
    return html.escape(text or "")


def _build_html(result: AnalysisResult) -> str:
    engines = "".join(
        f"<tr><td>{_esc(er.engine.value)}</td><td>{er.score}/100</td>"
        f"<td>{_esc(er.status.value)}</td><td>{_esc(er.rationale)}</td></tr>"
        for er in result.engine_readiness
    )
    recs = "".join(
        f"""<div class="rec">
          <div class="rec-head">
            <span class="badge" style="background:{_PRIORITY_COLOR.get(rec.priority.value, '#0f766e')}">
              {rec.priority.value}</span>
            <h3>{rec.priority_rank}. {_esc(rec.title)}</h3>
          </div>
          <p>{_esc(rec.description)}</p>
          <p><b>Why it matters:</b> {_esc(rec.why_it_matters)}</p>
          <p><b>Expected impact:</b> {_esc(rec.expected_impact)}</p>
          <p class="meta">Impact {rec.impact_score}/5 · Effort {_esc(rec.effort.value)} ·
             Confidence {rec.confidence}/5</p>
        </div>"""
        for rec in result.recommendations
    )
    a = result.alignment
    gaps = "".join(f"<li>{_esc(g)}</li>" for g in a.gaps)
    notes = (
        f"<div class='notes'><h2>Notes</h2><ul>{''.join(f'<li>{_esc(n)}</li>' for n in result.notes)}</ul></div>"
        if result.notes
        else ""
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
      * {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; color:#1e293b; }}
      body {{ margin:0; padding:40px; }}
      h1 {{ color:#0f2238; margin:0 0 4px; }}
      h2 {{ color:#0f2238; border-bottom:2px solid #0f9b8e; padding-bottom:4px; margin-top:28px; }}
      .url {{ color:#0f9b8e; font-size:13px; }}
      .meta-row {{ color:#64748b; font-size:12px; margin-top:6px; }}
      .score {{ font-size:48px; font-weight:700; color:#0f9b8e; }}
      table {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:8px; }}
      th,td {{ border:1px solid #e2e8f0; padding:6px 8px; text-align:left; }}
      th {{ background:#f1f5f9; }}
      .rec {{ border:1px solid #e2e8f0; border-radius:8px; padding:12px 16px; margin:10px 0;
              page-break-inside:avoid; }}
      .rec-head {{ display:flex; align-items:center; gap:8px; }}
      .rec h3 {{ margin:0; font-size:15px; }}
      .badge {{ color:#fff; font-weight:700; font-size:11px; padding:2px 8px; border-radius:4px; }}
      .meta {{ color:#64748b; font-size:12px; }}
      p {{ font-size:13px; line-height:1.5; margin:6px 0; }}
    </style></head><body>
      <h1>GEO Analysis Report</h1>
      <div class="url">{_esc(result.url)}</div>
      <div class="meta-row">mode: {_esc(result.mode.value)} · model: {_esc(result.model_key)} ·
        engines: {_esc(', '.join(e.value for e in result.target_engines))}</div>
      <div class="score">{result.overall_score}<span style="font-size:16px;color:#94a3b8">/100</span></div>
      <h2>Executive summary</h2>
      <p>{_esc(result.executive_summary)}</p>
      <h2>Citation readiness by engine</h2>
      <table><tr><th>Engine</th><th>Score</th><th>Status</th><th>Rationale</th></tr>{engines}</table>
      <h2>Strategic alignment</h2>
      <p><b>Goal alignment:</b> {a.goal_alignment_score}/100 — {_esc(a.goal_alignment_summary)}</p>
      <p><b>Query coverage:</b> {a.query_coverage_score}/100 — {_esc(a.query_coverage_summary)}</p>
      {f'<p><b>Gaps:</b></p><ul>{gaps}</ul>' if gaps else ''}
      <h2>Prioritized recommendations</h2>
      {recs}
      {notes}
    </body></html>"""


async def render_pdf(result: AnalysisResult) -> bytes:
    from playwright.async_api import async_playwright

    doc = _build_html(result)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(doc, wait_until="networkidle")
        pdf = await page.pdf(format="A4", print_background=True, margin={"top": "0", "bottom": "0"})
        await browser.close()
    return pdf
