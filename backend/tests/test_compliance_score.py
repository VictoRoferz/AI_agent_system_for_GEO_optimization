from app.analysis.claims import compliance_score
from app.analysis.schemas import Claim, ClaimFlag


def _claim(flag, claim_type):
    return Claim(text="x", flag=flag, claim_type=claim_type, rationale="r")


def test_empty_and_all_green_are_perfect():
    assert compliance_score([]) == 100
    assert compliance_score([_claim(ClaimFlag.GREEN, "efficacy")]) == 100


def test_weighted_penalties():
    # 3 red efficacy (18 ea = 54) + 5 yellow company_brand (2 ea = 10) + 8 green (0) -> 100-64
    claims = (
        [_claim(ClaimFlag.RED, "efficacy")] * 3
        + [_claim(ClaimFlag.YELLOW, "company_brand")] * 5
        + [_claim(ClaimFlag.GREEN, "statistic")] * 8
    )
    assert compliance_score(claims) == 36


def test_medical_red_costs_more_than_other_red():
    med = compliance_score([_claim(ClaimFlag.RED, "safety")])      # 100-18
    other = compliance_score([_claim(ClaimFlag.RED, "company_brand")])  # 100-8
    assert med == 82 and other == 92


def test_score_clamped_at_zero():
    assert compliance_score([_claim(ClaimFlag.RED, "efficacy")] * 50) == 0
