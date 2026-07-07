"""Plan phase: decide per-block actions, net-new sections, technical work and the
style brief that keeps parallel rewrite batches in one voice.

quick depth → pure heuristic plan (no LLM). full depth → one Senior GEO Strategist
call, falling back to the heuristic on any failure (the plan phase never aborts a run).
"""
from __future__ import annotations

from app.agent.prompts import PLANNER
from app.agent.schemas import BlockPlanItem, OptimizationPlan
from app.analysis.schemas import AnalysisResult, PageSignals


def default_plan(page: PageSignals) -> OptimizationPlan:
    """Deterministic fallback: rewrite every block in document order; add the
    obviously-missing technical elements."""
    technical: list[str] = []
    if not page.has_jsonld:
        technical.append("Add JSON-LD structured data appropriate for the page type")
    if not page.meta_description:
        technical.append("Add a meta description that answers the primary query")
    if not page.title:
        technical.append("Add a descriptive, query-aligned title tag")
    return OptimizationPlan(
        strategy_summary=(
            "Heuristic plan: rewrite every content block for answer-first, extractable, "
            "compliant copy; fill missing technical elements."
        ),
        style_brief=(
            "Preserve the page's factual meaning, product names and medical terminology "
            "exactly. Clear, factual, non-promotional tone suitable for regulated "
            "healthcare content; short answer-first sentences; address the target "
            "queries directly."
        ),
        block_plan=[BlockPlanItem(anchor_id=b.id, action="rewrite") for b in page.text_blocks],
        new_sections=[],
        technical_plan=technical,
        source="heuristic",
    )


def _planner_user(result: AnalysisResult, page: PageSignals) -> str:
    blocks = "\n".join(f"- {b.id} [{b.tag}]: {b.text}" for b in page.text_blocks) or "(none)"
    queries = "\n".join(f"- {q}" for q in result.queries) or "(none provided)"
    claims_red = sum(1 for c in result.claims if c.flag.value == "red")
    claims_yellow = sum(1 for c in result.claims if c.flag.value == "yellow")
    headings = "\n".join(f"  - {h}" for h in page.headings[:30]) or "  (none)"
    return (
        f"## Page\nURL: {page.final_url}\nTitle: {page.title or '(none)'}\n"
        f"Headings:\n{headings}\n\n"
        f"## Content blocks (decide an action for every id)\n{blocks}\n\n"
        f"## Target queries\n{queries}\n\n"
        f"## Prior analysis\nExecutive summary: {result.executive_summary}\n"
        f"Overall GEO score: {result.overall_score}/100 | compliance score: "
        f"{result.compliance_score}/100\n"
        f"Claim risks on page: {claims_red} red, {claims_yellow} yellow\n"
    )


async def make_plan(ctx, emit) -> OptimizationPlan:
    """ctx: AgentContext (engine). Emits its own step events."""
    from app.agent.engine import BudgetExceeded  # local import to avoid a cycle

    if not ctx.depth.plan_llm:
        plan = default_plan(ctx.page)
        emit_plan_step(ctx, emit, plan, note="heuristic (quick depth)")
        return plan
    ctx.step_started(emit, "plan", "plan.plan", "Planning the optimization", agent="strategist")
    try:
        plan = await ctx.llm(
            system=PLANNER,
            user=_planner_user(ctx.result, ctx.page),
            schema=OptimizationPlan,
            max_tokens=3000,
            temperature=0.2,
        )
        plan.source = "llm"
        if not plan.block_plan:  # a plan that plans nothing is not a plan
            plan.block_plan = [
                BlockPlanItem(anchor_id=b.id, action="rewrite") for b in ctx.page.text_blocks
            ]
        ctx.step_completed(
            emit,
            "plan",
            "plan.plan",
            detail=plan.strategy_summary,
            meta={
                "agent": "strategist",
                "counts": {
                    "blocks planned": len(plan.block_plan),
                    "new sections": len(plan.new_sections),
                    "technical changes": len(plan.technical_plan),
                },
            },
        )
        return plan
    except BudgetExceeded:
        raise
    except Exception as exc:
        ctx.step_failed(emit, "plan", "plan.plan", detail=f"planner failed: {exc}")
        plan = default_plan(ctx.page)
        emit_plan_step(ctx, emit, plan, note="fallback heuristic plan after planner failure")
        return plan


def emit_plan_step(ctx, emit, plan: OptimizationPlan, note: str) -> None:
    ctx.step_started(emit, "plan", "plan.heuristic", "Preparing the work plan", agent="strategist")
    ctx.step_completed(
        emit,
        "plan",
        "plan.heuristic",
        detail=f"{note}: rewrite {len(plan.block_plan)} blocks, "
        f"{len(plan.technical_plan)} technical changes",
        meta={"agent": "strategist"},
    )
