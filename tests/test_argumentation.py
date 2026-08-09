import pytest


_XFAIL_REASON = "Phase 3-3 argumentation runtime is not implemented in this preparation Change Unit"


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_argumentation_claim_reason_evidence():
    """RED contract: 主張→理由→根拠の関係を構造化できること。"""
    raise NotImplementedError(_XFAIL_REASON)


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_argumentation_counterargument_and_limitation():
    """RED contract: 反証・反論・限定を主張と区別して保持できること。"""
    raise NotImplementedError(_XFAIL_REASON)


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_argumentation_implicit_premise_is_candidate_only():
    """RED contract: 暗黙前提を事実確定せずCandidateとして保持すること。"""
    raise NotImplementedError(_XFAIL_REASON)


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_argumentation_ambiguous_without_evidence():
    """RED contract: Evidence不足時に推測せずAMBIGUOUSとすること。"""
    raise NotImplementedError(_XFAIL_REASON)
