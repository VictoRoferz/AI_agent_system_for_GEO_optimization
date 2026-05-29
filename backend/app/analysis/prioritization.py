"""Turn raw brain findings into ranked, priority-bucketed recommendations.

Score = impact x confidence / effort. Higher = do sooner. Buckets map to P0..P3.
This keeps prioritization deterministic and transparent rather than asking the model
to assign priorities directly.
"""
from __future__ import annotations

from app.analysis.schemas import Effort, LLMFinding, Priority, Recommendation

_EFFORT_WEIGHT = {Effort.LOW: 1, Effort.MEDIUM: 2, Effort.HIGH: 3}


def _score(f: LLMFinding) -> float:
    return f.impact_score * f.confidence / _EFFORT_WEIGHT[f.effort]


def _bucket(score: float) -> Priority:
    if score >= 8:
        return Priority.P0
    if score >= 4:
        return Priority.P1
    if score >= 2:
        return Priority.P2
    return Priority.P3


def prioritize(findings: list[LLMFinding]) -> list[Recommendation]:
    ranked = sorted(findings, key=_score, reverse=True)
    recs: list[Recommendation] = []
    for i, f in enumerate(ranked, start=1):
        recs.append(
            Recommendation(
                **f.model_dump(),
                id=f"rec-{i}",
                priority=_bucket(_score(f)),
                priority_rank=i,
            )
        )
    return recs
