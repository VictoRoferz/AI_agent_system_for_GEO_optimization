from app.analysis.prioritization import prioritize
from app.analysis.schemas import (
    Effort,
    KBCoverageItem,
    KBCoverageStatus,
    LLMFinding,
)
from app.analysis.synthesis import _remap_kb_coverage


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


def _findings():
    # original order: idx0 low (P3, rank 3), idx1 quick-win (rank 1), idx2 medium (rank 2)
    return [
        _finding("low", 1, Effort.HIGH, 1),
        _finding("quick-win", 5, Effort.LOW, 5),
        _finding("medium", 3, Effort.MEDIUM, 3),
    ]


def test_remaps_finding_index_to_final_rec_id():
    findings = _findings()
    recs = prioritize(findings)
    rec_titles = {r.id: r.title for r in recs}

    items = [
        KBCoverageItem(factor="A", status=KBCoverageStatus.GAP, assessment="x", related_rec_ids=["2"]),
        KBCoverageItem(factor="B", status=KBCoverageStatus.PARTIAL, assessment="y", related_rec_ids=["1", "3"]),
        KBCoverageItem(factor="C", status=KBCoverageStatus.COVERED, assessment="z", related_rec_ids=[]),
    ]
    out = _remap_kb_coverage(items, findings)

    # finding position 2 (1-based) == "quick-win" == rec-1
    assert rec_titles[out[0].related_rec_ids[0]] == "quick-win"
    # positions 1 and 3 == "low" and "medium"
    assert {rec_titles[r] for r in out[1].related_rec_ids} == {"low", "medium"}
    assert out[2].related_rec_ids == []


def test_tolerates_rec_prefixes_and_bad_tokens():
    findings = _findings()
    items = [
        KBCoverageItem(
            factor="A",
            status=KBCoverageStatus.GAP,
            assessment="x",
            related_rec_ids=["#2", "rec-2", "finding-99", "garbage", "0"],
        ),
    ]
    out = _remap_kb_coverage(items, findings)
    # "#2"/"rec-2" -> valid (no duplicate); "finding-99"/"garbage"/"0" -> dropped
    assert out[0].related_rec_ids == ["rec-1"]
