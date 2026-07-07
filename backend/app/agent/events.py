"""Agent step events: the SSE timeline vocabulary + trace reduction. All pure."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

_MAX_DETAIL = 200
_MAX_FINDINGS = 6
_MAX_FINDING_LEN = 160


class AgentStepEvent(BaseModel):
    """One step transition. A repeated step_id is a status transition of that step."""
    run_id: str = ""
    phase: str  # plan | audit | rewrite | verify | assemble
    step_id: str
    title: str = ""
    detail: str | None = None
    status: str = "started"  # started | completed | failed | skipped
    ts: str = ""
    pct: int | None = None
    meta: dict | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def step_event(
    phase: str,
    step_id: str,
    status: str,
    *,
    title: str = "",
    detail: str | None = None,
    pct: int | None = None,
    meta: dict | None = None,
    run_id: str = "",
) -> AgentStepEvent:
    return AgentStepEvent(
        run_id=run_id,
        phase=phase,
        step_id=step_id,
        title=title,
        detail=detail,
        status=status,
        ts=_now(),
        pct=pct,
        meta=meta,
    )


def sse_payload(ev: AgentStepEvent) -> dict:
    """Wire shape: truncate bulky fields so events stay lean (house discipline)."""
    data = ev.model_dump(mode="json", exclude_none=True)
    detail = data.get("detail")
    if isinstance(detail, str) and len(detail) > _MAX_DETAIL:
        data["detail"] = detail[: _MAX_DETAIL - 1] + "…"
    meta = data.get("meta")
    if isinstance(meta, dict):
        findings = meta.get("findings")
        if isinstance(findings, list):
            meta["findings"] = [
                (f[: _MAX_FINDING_LEN - 1] + "…" if isinstance(f, str) and len(f) > _MAX_FINDING_LEN else f)
                for f in findings[:_MAX_FINDINGS]
            ]
    return data


def reduce_trace(steps: list[dict]) -> dict:
    """Summarize a completed trace: per-phase durations/counts, failures, totals."""
    phases: dict[str, dict] = {}
    bounds: dict[str, tuple[datetime, datetime]] = {}
    failed = 0
    for s in steps:
        phase = s.get("phase", "?")
        ph = phases.setdefault(phase, {"steps": 0, "failed": 0})
        status = s.get("status")
        if status == "started":
            ph["steps"] += 1
        if status == "failed":
            ph["failed"] += 1
            failed += 1
        try:
            ts = datetime.fromisoformat(s.get("ts") or "")
        except ValueError:
            continue
        lo, hi = bounds.get(phase, (ts, ts))
        bounds[phase] = (min(lo, ts), max(hi, ts))
    for phase, ph in phases.items():
        lo_hi = bounds.get(phase)
        ph["duration_ms"] = (
            max(0, int((lo_hi[1] - lo_hi[0]).total_seconds() * 1000)) if lo_hi else 0
        )
    return {
        "phases": phases,
        "total_steps": sum(p["steps"] for p in phases.values()),
        "failed_steps": failed,
    }
