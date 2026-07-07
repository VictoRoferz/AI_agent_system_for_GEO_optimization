"""Change-package rendering — every change with its why, scores and manual steps."""
from app.agent.assemble import render_change_package
from app.agent.schemas import (
    CitationJudgement,
    KBFactorSet,
    OptimizationResult,
    QueryJudgement,
    VerificationReport,
)
from app.analysis.schemas import (
    EngineReadiness,
    KBCoverageItem,
    KBCoverageStatus,
    PageRewrite,
    Rationale,
    RewriteBlock,
    SignalStatus,
    TargetEngine,
    VerificationOutcome,
)


def _optimization() -> OptimizationResult:
    return OptimizationResult(
        run_id="r1",
        depth="full",
        model_key="gpt",
        factor_set=KBFactorSet(kb_hash="h"),
        verification=VerificationReport(passed=3, revised=1, needs_human=1),
        citation_judgement=CitationJudgement(
            before=[EngineReadiness(engine=TargetEngine.CHATGPT, score=45,
                                    status=SignalStatus.PREDICTED, rationale="r")],
            after=[EngineReadiness(engine=TargetEngine.CHATGPT, score=75,
                                   status=SignalStatus.PREDICTED, rationale="r")],
            per_query=[QueryJudgement(query="what is X", before_would_cite=False,
                                      after_would_cite=True, reasoning="better")],
            summary="Predicted improvement.",
        ),
        kb_coverage=[KBCoverageItem(factor="Answer-first intro", status=KBCoverageStatus.COVERED,
                                    assessment="Good now.")],
        claims_addressed=2,
        stats={"llm_calls": 20},
    )


def _rewrite() -> PageRewrite:
    return PageRewrite(
        run_id="r1", summary="s", model_key="gpt", origin="agent",
        content_blocks=[
            RewriteBlock(
                id="blk-1", kind="paragraph", label="Intro", original="old", proposed="new",
                changed=True,
                rationale=Rationale(why="Answers the query directly",
                                    kb_factor_names=["Answer-first intro"],
                                    queries_targeted=["what is X"],
                                    expected_effect="higher extractability"),
                verification=VerificationOutcome(status="passed"),
            ),
        ],
        technical_blocks=[
            RewriteBlock(id="blk-2", kind="jsonld", label="JSON-LD schema", original="",
                         proposed='{"@type": "Article"}', changed=True, is_technical=True,
                         change_explanation="Adds machine-readable structure"),
        ],
    )


def test_change_package_contains_all_sections():
    md = render_change_package(_optimization(), _rewrite(), "https://x.test/p",
                               not_applied=["blk-9: apply robots.txt manually"])
    assert "# Optimized page — change package" in md
    assert "https://x.test/p" in md
    assert "| chatgpt | 45 | 75 | +30 |" in md
    assert "| what is X | no | yes |" in md
    assert "### Intro (blk-1) — passed" in md
    assert "Answers the query directly" in md
    assert "**KB factors:** Answer-first intro" in md
    assert "**Targets queries:** what is X" in md
    assert "JSON-LD schema" in md and '{"@type": "Article"}' in md
    assert "Adds machine-readable structure" in md
    assert "apply robots.txt manually" in md
    assert "| Answer-first intro | covered | Good now. |" in md
    assert "2 claim risk(s)" in md
