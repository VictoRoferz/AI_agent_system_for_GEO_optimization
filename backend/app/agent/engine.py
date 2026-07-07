"""The optimization-agent engine: phase sequencing, event streaming, persistence.

`run_optimization` is an async generator (same contract as analysis
`run_analysis`): it yields ("agent_step", AgentStepEvent), ("progress",
ProgressEvent) and finally ("result", slim dict). Phases run as a background
task and emit through an asyncio.Queue; the generator drains the queue,
persists the trace on every step (mid-run readable) and yields to SSE.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.agent.audit import claims_by_anchor, coverage_from_audits, merge_audit_findings, run_audits
from app.agent.budget import DEPTHS, DepthConfig
from app.agent.events import AgentStepEvent, reduce_trace, sse_payload, step_event
from app.agent.factors import factor_names_by_id, get_factor_set, render_factor_context
from app.agent.planner import make_plan
from app.agent.prompts import EXPERTS
from app.agent.rewriter import run_rewrite
from app.agent.schemas import (
    ExpertProfile,
    KBFactorSet,
    OptimizationResult,
    ScoreCard,
    VerificationReport,
)
from app.agent.verify import (
    BLOCKING_KINDS,
    apply_verification,
    run_citation_judge,
    run_deterministic_checks,
    run_llm_panel,
    run_revision,
)
from app.analysis.prioritization import prioritize
from app.analysis.schemas import (
    AnalysisRequest,
    AnalysisResult,
    GoalsDocument,
    PageRewrite,
    ProgressEvent,
    Rationale,
    Recommendation,
    RewriteBlock,
)
from app.analysis.signals import heuristic_baseline
from app.core.llm import complete_structured
from app.ingestion.kb_loader import load_kb_context
from app.storage import repository


class BudgetExceeded(RuntimeError):
    """Raised when the depth's hard LLM-call cap is reached."""


@dataclass
class AgentContext:
    run_id: str
    request: AnalysisRequest
    result: AnalysisResult
    page: object  # PageSignals
    goals: GoalsDocument | None
    kb_context: str
    depth: DepthConfig
    model_key: str
    factor_set: KBFactorSet | None = None
    cache_prefix: str = ""
    calls: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def goals_text(self) -> str | None:
        return self.goals.text if self.goals else None

    async def llm(self, **kwargs):
        """All agent LLM calls go through here: budget cap + shared cache prefix."""
        if self.calls >= self.depth.max_llm_calls:
            raise BudgetExceeded(
                f"LLM call budget exhausted ({self.depth.max_llm_calls} calls at "
                f"depth={self.depth.key})"
            )
        self.calls += 1
        return await complete_structured(
            model_key=self.model_key,
            cache_prefix=self.cache_prefix or None,
            **kwargs,
        )

    # ---- step-event helpers (emit = queue-backed callback set by the engine)
    def step_started(self, emit, phase, step_id, title, *, agent=None, meta=None, pct=None):
        meta = {**(meta or {})}
        if agent:
            meta["agent"] = agent
        emit(step_event(phase, step_id, "started", title=title, meta=meta or None,
                        pct=pct, run_id=self.run_id))

    def step_completed(self, emit, phase, step_id, *, detail=None, meta=None, pct=None):
        emit(step_event(phase, step_id, "completed", detail=detail, meta=meta,
                        pct=pct, run_id=self.run_id))

    def step_failed(self, emit, phase, step_id, *, detail=None, meta=None):
        emit(step_event(phase, step_id, "failed", detail=detail, meta=meta, run_id=self.run_id))

    def step_skipped(self, emit, phase, step_id, title, *, detail=None, meta=None):
        emit(step_event(phase, step_id, "skipped", title=title, detail=detail, meta=meta,
                        run_id=self.run_id))


# --------------------------------------------------------- deterministic finalize
def link_recs_to_blocks(recs: list[Recommendation], blocks: list[RewriteBlock]) -> None:
    """Pure. Fill Recommendation.block_ids by inverting block rationale.recommendation_ids."""
    by_rec: dict[str, list[str]] = {}
    for b in blocks:
        if not b.changed or not b.rationale:
            continue
        for rid in b.rationale.recommendation_ids:
            token = rid.strip().lstrip("#")
            by_rec.setdefault(token, []).append(b.id)
    for rec in recs:
        rec.block_ids = by_rec.get(rec.id, [])


def resolve_rationale_names(rationale: Rationale | None, names: dict[str, str]) -> None:
    """Pure. Fill kb_factor_names from ids (names == KBCoverageItem.factor, the UI join key)."""
    if rationale is None:
        return
    rationale.kb_factor_ids = [f for f in rationale.kb_factor_ids if f in names]
    rationale.kb_factor_names = [names[f] for f in rationale.kb_factor_ids]


# --------------------------------------------------------------------- the engine
async def _execute(ctx: AgentContext, emit) -> tuple[OptimizationResult, PageRewrite]:
    t0 = time.monotonic()

    # Phase: factors (cached — usually instant after the first run on this KB)
    ctx.step_started(emit, "plan", "plan.factors", "Loading the canonical KB factor list",
                     agent="strategist", pct=5)
    factor_set = await get_factor_set(ctx.kb_context, ctx.model_key)
    ctx.factor_set = factor_set
    ctx.cache_prefix = f"{ctx.kb_context}\n\n{render_factor_context(factor_set)}"
    ctx.step_completed(emit, "plan", "plan.factors", pct=8,
                       meta={"agent": "strategist",
                             "counts": {"factors": len(factor_set.factors)}})

    # Phase: plan
    plan = await make_plan(ctx, emit)

    # Phase: audit (expert panel) + claims
    audits, claims = await run_audits(ctx, emit)
    findings = merge_audit_findings(audits)
    recs = prioritize(findings)

    # Phase: rewrite (every block, batched) + technical + net-new
    cba = claims_by_anchor(claims)
    content_blocks, technical_blocks = await run_rewrite(ctx, emit, plan, recs, cba)
    all_blocks = [*content_blocks, *technical_blocks]

    # Phase: verify — deterministic checks first (free), then the expert panel.
    ctx.step_started(emit, "verify", "verify.checks",
                     "Running deterministic verification checks", agent="fidelity", pct=80)
    issues = run_deterministic_checks(ctx.page, recs, content_blocks, technical_blocks)
    issues_by_block: dict[str, list] = {}
    for issue in issues:
        if issue.block_id:
            issues_by_block.setdefault(issue.block_id, []).append(issue)
    ctx.step_completed(
        emit, "verify", "verify.checks", pct=83,
        meta={"agent": "fidelity", "counts": {"issues": len(issues)}},
    )

    # LLM panel: Domain Fidelity Guardian (+ Compliance Officer at full depth).
    verdicts = await run_llm_panel(ctx, emit, all_blocks, claims)
    suggested: dict[str, str] = {}
    for v in verdicts:
        if v.issues:
            issues_by_block.setdefault(v.block_id, []).extend(v.issues)
        if v.verdict != "pass" and v.suggested_fix:
            suggested[v.block_id] = v.suggested_fix

    # Blocks with blocking issues → one revision loop (full depth only).
    def blocking_ids() -> dict[str, list]:
        return {
            bid: blk_issues
            for bid, blk_issues in issues_by_block.items()
            if any(i.kind in BLOCKING_KINDS for i in blk_issues)
        }

    statuses: dict[str, str] = {}
    to_fix = blocking_ids()
    if ctx.depth.revision_loop and to_fix:
        revised = await run_revision(ctx, emit, all_blocks, to_fix, suggested)
        if revised:
            # Re-check the revised blocks; cleared issues → "revised", else needs_human.
            recheck = run_deterministic_checks(ctx.page, recs, content_blocks, technical_blocks)
            still_blocking = {
                i.block_id for i in recheck if i.block_id in revised and i.kind in BLOCKING_KINDS
            }
            for bid in revised:
                if bid in still_blocking:
                    statuses[bid] = "needs_human"
                else:
                    statuses[bid] = "revised"
                    issues_by_block.pop(bid, None)
    report: VerificationReport = apply_verification(all_blocks, issues_by_block, statuses)
    ctx.step_started(emit, "verify", "verify.summary", "Consolidating verification results",
                     agent="fidelity", pct=90)
    ctx.step_completed(
        emit, "verify", "verify.summary", pct=91,
        meta={"agent": "fidelity",
              "counts": {"passed": report.passed, "revised": report.revised,
                         "needs review": report.needs_human}},
    )

    # LLM Retrieval Expert: before/after citation-readiness (PREDICTED).
    judgement = await run_citation_judge(ctx, emit, all_blocks)

    # Phase: assemble (deterministic linking, naming, coverage, scores)
    ctx.step_started(emit, "assemble", "assemble.finalize",
                     "Linking recommendations, coverage and rationales", agent="strategist", pct=93)
    names = factor_names_by_id(factor_set)
    for b in all_blocks:
        resolve_rationale_names(b.rationale, names)
    for rec in recs:
        resolve_rationale_names(rec.rationale, names)
    link_recs_to_blocks(recs, all_blocks)
    coverage = coverage_from_audits(audits, factor_set, recs, all_blocks)

    rewrite = PageRewrite(
        run_id=ctx.run_id,
        summary=plan.strategy_summary or "Agent optimization run",
        content_blocks=content_blocks,
        technical_blocks=technical_blocks,
        model_key=ctx.model_key,
        origin="agent",
    )
    before = ScoreCard(
        overall_score=ctx.result.overall_score,
        heuristic_baseline=heuristic_baseline(ctx.page),
        compliance_score=ctx.result.compliance_score,
        engine_readiness=ctx.result.engine_readiness,
    )
    after = ScoreCard()
    if judgement is not None and judgement.after:
        after.engine_readiness = judgement.after
        after.overall_score = round(
            sum(er.score for er in judgement.after) / len(judgement.after)
        )

    changed = sum(1 for b in all_blocks if b.changed)
    optimization = OptimizationResult(
        run_id=ctx.run_id,
        depth=ctx.depth.key,
        model_key=ctx.model_key,
        experts=[ExpertProfile(id=e.id, name=e.name, role=e.role) for e in EXPERTS.values()],
        factor_set=factor_set,
        plan=plan,
        audits=audits,
        recommendations=recs,
        kb_coverage=coverage,
        claims=claims,
        verification=report,
        citation_judgement=judgement,
        before=before,
        after=after,
        claims_addressed=_claims_addressed(claims, content_blocks),
        stats={
            "llm_calls": ctx.calls,
            "wall_ms": int((time.monotonic() - t0) * 1000),
            "blocks_total": len(all_blocks),
            "blocks_changed": changed,
            "findings": len(findings),
        },
        notes=ctx.notes,
    )
    ctx.step_completed(
        emit, "assemble", "assemble.finalize", pct=98,
        meta={"agent": "strategist",
              "counts": {"recommendations": len(recs), "blocks changed": changed,
                         "factors covered": sum(1 for c in coverage if c.status.value == "covered")}},
    )
    return optimization, rewrite


def _claims_addressed(claims, content_blocks: list[RewriteBlock]) -> int:
    """Deterministic: red/yellow claims whose anchored block was changed."""
    changed_anchors = {b.anchor_id for b in content_blocks if b.changed and b.anchor_id}
    return sum(
        1 for c in claims if c.flag.value in ("red", "yellow") and c.anchor_id in changed_anchors
    )


async def run_optimization(
    run_id: str,
    request: AnalysisRequest,
    result: AnalysisResult,
    depth_key: str,
    model_key: str,
    goals: GoalsDocument | None = None,
):
    """Async generator: yields ('agent_step', ev) / ('progress', ProgressEvent) /
    ('result', slim dict). Persists trace per step, rewrite + OptimizationResult at end."""
    depth = DEPTHS.get(depth_key, DEPTHS["quick"])
    ctx = AgentContext(
        run_id=run_id,
        request=request,
        result=result,
        page=result.page_signals,
        goals=goals,
        kb_context=load_kb_context(),
        depth=depth,
        model_key=model_key,
    )

    queue: asyncio.Queue = asyncio.Queue()

    def emit(ev: AgentStepEvent) -> None:
        queue.put_nowait(("step", ev))

    async def runner() -> None:
        try:
            pair = await _execute(ctx, emit)
            queue.put_nowait(("done", pair))
        except Exception as exc:  # surfaced as an SSE error by the caller
            queue.put_nowait(("error", exc))

    await repository.save_agent_run(run_id, status="running", depth=depth.key, model_key=model_key)
    task = asyncio.create_task(runner())
    steps: list[dict] = []

    async def persist_trace(status: str) -> None:
        await repository.upsert_agent_trace(
            run_id,
            status=status,
            depth=depth.key,
            model_key=model_key,
            steps=steps,
            summary=reduce_trace(steps) if status != "running" else None,
        )

    try:
        yield "progress", ProgressEvent(step="agent", message="Optimization agent started…", pct=2)
        while True:
            kind, payload = await queue.get()
            if kind == "step":
                data = sse_payload(payload)
                steps.append(data)
                await persist_trace("running")
                yield "agent_step", payload
            elif kind == "done":
                optimization, rewrite = payload
                await repository.upsert_rewrite(run_id, rewrite)
                await repository.save_agent_run(
                    run_id, status="completed", depth=depth.key, model_key=model_key,
                    result=optimization.model_dump(mode="json"),
                )
                await persist_trace("completed")
                yield "progress", ProgressEvent(step="done", message="Optimization complete.", pct=100)
                yield "result", _slim_result(optimization)
                return
            else:  # error
                exc: Exception = payload
                await repository.save_agent_run(
                    run_id, status="error", depth=depth.key, model_key=model_key, error=str(exc)
                )
                await persist_trace("error")
                raise exc
    finally:
        if not task.done():
            task.cancel()


def _slim_result(optimization: OptimizationResult) -> dict:
    """The SSE result payload — artifacts are refetched, not streamed (bulk discipline)."""
    return {
        "run_id": optimization.run_id,
        "depth": optimization.depth,
        "stats": optimization.stats,
        "before": optimization.before.model_dump(mode="json"),
        "after": optimization.after.model_dump(mode="json"),
        "verification": optimization.verification.model_dump(mode="json"),
        "claims_addressed": optimization.claims_addressed,
    }
