"""Verification phase — deterministic checks, backfills, verdict sanitization,
blocking-vs-advisory stamping."""
from app.agent.schemas import BlockVerdict
from app.agent.verify import (
    apply_verification,
    check_forbidden_phrases,
    check_no_new_numbers,
    check_rec_coverage,
    check_flag_quotes,
    ensure_explanations,
    inherit_factor_ids,
    sanitize_verdicts,
)
from app.analysis.prioritization import prioritize
from app.analysis.schemas import (
    ChangeType,
    ConcreteChange,
    Effort,
    LLMFinding,
    PageSignals,
    ProposedFlag,
    ClaimFlag,
    Rationale,
    RewriteBlock,
    TextBlock,
    VerificationIssue,
)


def _page(text: str = "The device has a 40-year history. 90% satisfaction was reported.") -> PageSignals:
    return PageSignals(
        final_url="https://x.test",
        main_text=text,
        text_blocks=[TextBlock(id="g1", tag="p", text=text)],
    )


def _block(
    bid: str = "blk-1",
    original: str = "The device has a 40-year history.",
    proposed: str = "The device has a documented 40-year history.",
    **kw,
) -> RewriteBlock:
    return RewriteBlock(
        id=bid, kind="paragraph", label="p", original=original, proposed=proposed,
        changed=True, anchor_id="g1", **kw,
    )


def _finding(factors: list[str]) -> LLMFinding:
    return LLMFinding(
        title="Fix intro", description="d", why_it_matters="w", expected_impact="e",
        impact_score=5, effort=Effort.LOW, confidence=5,
        change=ConcreteChange(change_type=ChangeType.CONTENT, target="Intro"),
        rationale=Rationale(why="w", kb_factor_ids=factors),
    )


def test_no_new_numbers_catches_invented_stats():
    issues = check_no_new_numbers(_page(), [_block(proposed="Studies show 97% success.")])
    assert [i.kind for i in issues] == ["new_number"]
    assert issues[0].quote == "97%"
    # numbers already on the page pass
    assert check_no_new_numbers(_page(), [_block(proposed="90% satisfaction was reported here.")]) == []


def test_forbidden_phrases_only_when_introduced():
    bad = _block(proposed="This is the best implant available.")
    assert [i.kind for i in check_forbidden_phrases([bad])] == ["compliance_lexicon"]
    # already present in the original → not our regression
    ok = _block(original="It is the best.", proposed="It is the best device.")
    assert check_forbidden_phrases([ok]) == []
    # word boundary: "bestowed" must not match "best"
    assert check_forbidden_phrases([_block(proposed="An honor bestowed annually.")]) == []


def test_rec_coverage_flags_unimplemented_p0():
    recs = prioritize([_finding(["f-1"])])
    unimplemented = check_rec_coverage(recs, [_block(rationale=Rationale(why="w"))])
    assert [i.kind for i in unimplemented] == ["rec_unimplemented"]
    implemented = check_rec_coverage(
        recs, [_block(rationale=Rationale(why="w", recommendation_ids=["rec-1"]))]
    )
    assert implemented == []


def test_flag_quotes_dropped_when_not_verbatim():
    b = _block(flags=[
        ProposedFlag(quote="documented 40-year history", flag=ClaimFlag.YELLOW),
        ProposedFlag(quote="not in the text", flag=ClaimFlag.RED),
    ])
    issues, dropped = check_flag_quotes([b])
    assert dropped == 1
    assert len(b.flags) == 1


def test_inherit_factor_ids_and_ensure_explanations():
    recs = prioritize([_finding(["f-3", "f-7"])])
    b = _block(rationale=Rationale(why="improves answers", recommendation_ids=["rec-1"]),
               change_explanation=None)
    assert inherit_factor_ids([b], recs) == 1
    assert b.rationale.kb_factor_ids == ["f-3", "f-7"]
    assert ensure_explanations([b]) == 1
    assert b.change_explanation == "improves answers"


def test_apply_verification_blocking_vs_advisory():
    blocking = _block("blk-1")
    advisory = _block("blk-2")
    untouched = _block("blk-3")
    untouched.changed = False
    report = apply_verification(
        [blocking, advisory, untouched],
        {
            "blk-1": [VerificationIssue(kind="new_number", detail="d", block_id="blk-1")],
            "blk-2": [VerificationIssue(kind="missing_rationale", detail="d", block_id="blk-2")],
        },
        {},
    )
    assert blocking.verification.status == "needs_human"
    assert advisory.verification.status == "passed"  # advisory attaches, doesn't block
    assert advisory.verification.issues
    assert untouched.verification is None
    assert report.passed == 1 and report.needs_human == 1
    assert report.by_kind == {"new_number": 1, "missing_rationale": 1}
    # explicit statuses (revision loop) win
    report2 = apply_verification([_block("blk-9")], {}, {"blk-9": "revised"})
    assert report2.revised == 1


def test_sanitize_verdicts_requires_verbatim_quotes_and_known_blocks():
    blocks = [_block("blk-1", proposed="A documented 40-year history.")]
    verdicts = sanitize_verdicts(
        [
            BlockVerdict(block_id="blk-1", verdict="fail", issues=[
                VerificationIssue(kind="meaning_drift", detail="d", quote="documented"),
                VerificationIssue(kind="unsupported_claim", detail="d", quote="NOT PRESENT"),
            ]),
            BlockVerdict(block_id="blk-404", verdict="fail"),
            BlockVerdict(block_id="blk-1", verdict="pass"),  # duplicate dropped
        ],
        blocks,
    )
    assert len(verdicts) == 1
    assert verdicts[0].verdict == "fail"
    assert len(verdicts[0].issues) == 1  # non-verbatim quote discarded
    # a non-pass verdict whose issues all died downgrades to pass
    downgraded = sanitize_verdicts(
        [BlockVerdict(block_id="blk-1", verdict="revise", issues=[
            VerificationIssue(kind="compliance", detail="d", quote="NOPE")
        ])],
        blocks,
    )
    assert downgraded[0].verdict == "pass"
