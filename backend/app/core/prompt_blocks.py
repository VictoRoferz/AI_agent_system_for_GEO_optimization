"""Shared prompt fragments — single source of truth for cross-cutting rules.

Extracted VERBATIM from the synthesis / rewrite system prompts so the analysis
pipeline and the optimization agent enforce byte-identical compliance rules.
A unit test asserts every agent prompt embeds these blocks unchanged.
"""
from __future__ import annotations

# Analysis-facing compliance rules (from analysis/synthesis.py::_SYSTEM).
COMPLIANCE_BLOCK = """REGULATED-INDUSTRY COMPLIANCE — ALWAYS APPLY. Treat the page as regulated pharma / medtech / \
biotech / healthcare content. Never use or propose unsubstantiated promotional or marketing \
language. Every efficacy, safety, superiority or outcome claim MUST be backed by a citable \
study, clinical data or regulatory approval (FDA/EMA/MDR); if the page lacks supporting \
evidence, do NOT invent a claim — instead recommend adding the evidence/citation, or soften it \
to a compliant, factual statement. Avoid absolute or comparative claims ("best", "cure", \
"guaranteed", "#1", "superior to X") without head-to-head evidence, and avoid off-label \
implications. Flag any existing non-compliant claim on the page as a P0-level risk (high \
impact_score) with a concrete compliant rewrite. All `change` copy you propose must itself be \
compliant."""

# Writing-facing compliance rules (from analysis/rewrite.py::_REWRITE_SYSTEM).
COMPLIANCE_BLOCK_REWRITE = """REGULATED-INDUSTRY COMPLIANCE — ALWAYS APPLY. Treat the page as regulated pharma / medtech / \
biotech / healthcare content. Every word you propose must be compliant: no unsubstantiated \
promotional or marketing language; every efficacy, safety, superiority or outcome claim must \
be backed by a citable study, clinical data or regulatory approval present on the page — if \
the evidence is not there, do NOT assert the claim (state it factually, add a citation \
placeholder, or soften it). Avoid absolute/comparative claims ("best", "cure", "guaranteed", \
"#1", "superior to X") without head-to-head evidence, and avoid off-label implications. If the \
original text contains a non-compliant claim, rewrite it into a compliant version and explain \
that in `change_explanation`."""

# Concrete-change contract (from analysis/synthesis.py::_SYSTEM).
CONCRETE_CHANGE_BLOCK = """CRITICAL — every recommendation MUST be concrete and immediately usable via its `change` \
object, never vague advice:
  * If the recommendation is about COPY/CONTENT (title, heading, meta description, a \
paragraph), set change.change_type="content", change.target (where on the page), \
change.original_text (quote the current text verbatim, or "" if it does not exist yet), and \
change.proposed_text (the ACTUAL rewritten text, ready to paste — not a description of it).
  * If the recommendation is TECHNICAL (JSON-LD/schema, meta/link tags, markup, canonical, \
robots/llms.txt), set change.change_type="technical", change.target, change.code_language \
("html"|"json"|"jsonld"), change.code_snippet (the EXACT code to paste, fully formed), and \
change.instructions (clear step-by-step on where and how to apply it).
Fill in the real values for the chosen branch; leave the other branch's fields null."""
