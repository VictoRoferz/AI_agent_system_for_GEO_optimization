"""Audit post-processing — sanitization, dedup merge, coverage, claim grouping."""
from app.agent.audit import (
    claims_by_anchor,
    coverage_from_audits,
    merge_audit_findings,
    sanitize_audits,
)
from app.agent.factors import assign_factor_ids
from app.agent.schemas import AuditFinding, FactorAudit, KBFactor, KBFactorSet
from app.analysis.prioritization import prioritize
from app.analysis.schemas import (
    Claim,
    ClaimFlag,
    ConcreteChange,
    ChangeType,
    Effort,
    EvidenceRef,
    PageSignals,
    Rationale,
    RewriteBlock,
    TextBlock,
)


def _page() -> PageSignals:
    return PageSignals(
        final_url="https://x.test/a",
        main_text="Cochlear implants restore hearing pathways. 90% of users report benefit.",
        text_blocks=[
            TextBlock(id="g1", tag="p", text="Cochlear implants restore hearing pathways."),
            TextBlock(id="g2", tag="p", text="90% of users report benefit."),
        ],
    )


def _finding(title: str, target: str = "", impact: int = 3, factors: list[str] | None = None) -> AuditFinding:
    return AuditFinding(
        title=title,
        description="d",
        why_it_matters="w",
        expected_impact="e",
        impact_score=impact,
        effort=Effort.LOW,
        confidence=4,
        change=ConcreteChange(change_type=ChangeType.CONTENT, target=target) if target else None,
        rationale=Rationale(why="why", kb_factor_ids=factors or ["f-1"]),
    )


def _factors() -> list[KBFactor]:
    return assign_factor_ids(
        [KBFactor(name="Answer-first intro"), KBFactor(name="Cited statistics")]
    )


def test_sanitize_backfills_missing_factors_and_drops_invented_ids():
    factors = _factors()
    audits = [
        FactorAudit(factor_id=factors[0].id, status="gap", assessment="a"),
        FactorAudit(factor_id="f-999", status="covered", assessment="invented"),
    ]
    out = sanitize_audits(audits, factors, _page(), "content")
    assert [a.factor_id for a in out] == [f.id for f in factors]
    assert out[0].status == "gap"
    assert out[1].status == "error"  # missing from the model's answer


def test_sanitize_drops_non_verbatim_quotes_and_stamps_agent():
    factors = _factors()[:1]
    audits = [
        FactorAudit(
            factor_id=factors[0].id,
            status="partial",
            assessment="a",
            evidence_quotes=[
                EvidenceRef(quote="Cochlear implants restore hearing pathways."),
                EvidenceRef(quote="This sentence is NOT on the page."),
                EvidenceRef(quote="no JSON-LD found", source="signal"),
            ],
            findings=[_finding("Add intro", factors=[])],
        )
    ]
    out = sanitize_audits(audits, factors, _page(), "technical")
    assert len(out[0].evidence_quotes) == 2  # page-verbatim + signal kept, fabricated dropped
    assert out[0].findings[0].source_agent == "technical"
    assert out[0].findings[0].rationale.kb_factor_ids[0] == factors[0].id  # backfilled


def test_merge_dedups_same_target_similar_title_keeps_higher_impact():
    a = FactorAudit(
        factor_id="f-1", status="gap", assessment="",
        findings=[_finding("Add answer-first intro paragraph", "Intro paragraph", impact=3, factors=["f-1"])],
    )
    b = FactorAudit(
        factor_id="f-2", status="gap", assessment="",
        findings=[_finding("Add an answer-first intro paragraph now", "Intro paragraph", impact=5, factors=["f-2"])],
    )
    merged = merge_audit_findings([a, b])
    assert len(merged) == 1
    assert merged[0].impact_score == 5
    assert set(merged[0].rationale.kb_factor_ids) == {"f-1", "f-2"}


def test_merge_keeps_distinct_findings():
    a = FactorAudit(factor_id="f-1", status="gap", assessment="",
                    findings=[_finding("Add JSON-LD schema", "<head>")])
    b = FactorAudit(factor_id="f-2", status="gap", assessment="",
                    findings=[_finding("Rewrite the intro for answers", "Intro")])
    assert len(merge_audit_findings([a, b])) == 2


def test_coverage_links_recs_and_blocks_per_factor():
    factors = _factors()
    fs = KBFactorSet(kb_hash="h", factors=factors)
    audits = [
        FactorAudit(factor_id=factors[0].id, status="gap", assessment="missing intro"),
        FactorAudit(factor_id=factors[1].id, status="covered", assessment="ok"),
    ]
    recs = prioritize([_finding("Fix intro", "Intro", impact=5, factors=[factors[0].id])])
    blocks = [
        RewriteBlock(id="blk-1", kind="paragraph", label="Intro", original="a", proposed="b",
                     changed=True, rationale=Rationale(why="w", kb_factor_ids=[factors[0].id])),
    ]
    cov = coverage_from_audits(audits, fs, recs, blocks)
    assert len(cov) == 2
    first = next(c for c in cov if c.factor_id == factors[0].id)
    assert first.status.value == "gap"
    assert first.related_rec_ids == ["rec-1"]
    assert first.related_block_ids == ["blk-1"]
    second = next(c for c in cov if c.factor_id == factors[1].id)
    assert second.status.value == "covered" and second.related_rec_ids == []


def test_claims_by_anchor_groups_red_yellow_only():
    claims = [
        Claim(text="a", flag=ClaimFlag.RED, claim_type="efficacy", rationale="r", anchor_id="g1"),
        Claim(text="b", flag=ClaimFlag.YELLOW, claim_type="statistic", rationale="r", anchor_id="g1"),
        Claim(text="c", flag=ClaimFlag.GREEN, claim_type="other", rationale="r", anchor_id="g2"),
        Claim(text="d", flag=ClaimFlag.RED, claim_type="safety", rationale="r", anchor_id=None),
    ]
    grouped = claims_by_anchor(claims)
    assert set(grouped.keys()) == {"g1"}
    assert len(grouped["g1"]) == 2
