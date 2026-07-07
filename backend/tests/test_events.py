"""Agent step events: lifecycle, wire truncation, trace reduction."""
from app.agent.events import reduce_trace, sse_payload, step_event


def test_step_event_carries_timestamp_and_meta():
    ev = step_event("audit", "audit.g1", "started", title="T", meta={"agent": "technical"})
    assert ev.ts and ev.phase == "audit" and ev.status == "started"
    assert ev.meta == {"agent": "technical"}


def test_sse_payload_truncates_detail_and_findings():
    ev = step_event(
        "audit", "audit.g1", "completed",
        detail="x" * 500,
        meta={"findings": ["f" * 500] + [f"n{i}" for i in range(10)]},
    )
    data = sse_payload(ev)
    assert len(data["detail"]) <= 200
    assert len(data["meta"]["findings"]) <= 6
    assert all(len(f) <= 160 for f in data["meta"]["findings"])


def test_sse_payload_excludes_none_fields():
    data = sse_payload(step_event("plan", "plan.plan", "started", title="T"))
    assert "detail" not in data and "meta" not in data and "pct" not in data


def test_reduce_trace_counts_per_phase():
    steps = [
        {"phase": "audit", "step_id": "a", "status": "started", "ts": "2026-07-07T10:00:00+00:00"},
        {"phase": "audit", "step_id": "a", "status": "completed", "ts": "2026-07-07T10:00:08+00:00"},
        {"phase": "audit", "step_id": "b", "status": "started", "ts": "2026-07-07T10:00:01+00:00"},
        {"phase": "audit", "step_id": "b", "status": "failed", "ts": "2026-07-07T10:00:05+00:00"},
        {"phase": "rewrite", "step_id": "c", "status": "started", "ts": "2026-07-07T10:00:09+00:00"},
        {"phase": "rewrite", "step_id": "c", "status": "completed", "ts": "2026-07-07T10:00:20+00:00"},
    ]
    summary = reduce_trace(steps)
    assert summary["total_steps"] == 3
    assert summary["failed_steps"] == 1
    assert summary["phases"]["audit"]["steps"] == 2
    assert summary["phases"]["audit"]["failed"] == 1
    assert summary["phases"]["audit"]["duration_ms"] == 8000
    assert summary["phases"]["rewrite"]["duration_ms"] == 11000
