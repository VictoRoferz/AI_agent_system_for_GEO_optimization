from app.analysis.prioritization import prioritize
from app.analysis.schemas import Effort, LLMFinding, Priority


def _finding(title, impact, effort, conf):
    return LLMFinding(
        title=title,
        description="d",
        why_it_matters="w",
        expected_impact="i",
        impact_score=impact,
        effort=effort,
        confidence=conf,
    )


def test_high_impact_low_effort_ranks_first_and_is_p0():
    findings = [
        _finding("low-value", 1, Effort.HIGH, 1),       # score 0.33 -> P3
        _finding("quick-win", 5, Effort.LOW, 5),         # score 25 -> P0, rank 1
        _finding("medium", 3, Effort.MEDIUM, 3),         # score 4.5 -> P1
    ]
    recs = prioritize(findings)
    assert recs[0].title == "quick-win"
    assert recs[0].priority == Priority.P0
    assert recs[0].priority_rank == 1
    assert recs[-1].priority == Priority.P3
    # ranks are unique and sequential
    assert [r.priority_rank for r in recs] == [1, 2, 3]


def test_bucket_thresholds():
    # score exactly 8 -> P0 ; 4 -> P1 ; 2 -> P2
    recs = prioritize(
        [
            _finding("p0", 4, Effort.MEDIUM, 4),  # 16/2 = 8
            _finding("p1", 4, Effort.MEDIUM, 2),  # 8/2 = 4
            _finding("p2", 2, Effort.MEDIUM, 2),  # 4/2 = 2
        ]
    )
    by_title = {r.title: r.priority for r in recs}
    assert by_title["p0"] == Priority.P0
    assert by_title["p1"] == Priority.P1
    assert by_title["p2"] == Priority.P2
