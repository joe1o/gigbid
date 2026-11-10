import pytest
from pydantic import ValidationError

from agent.handoffs import ApprovalDecision, BidDecision, FitReport, RiskReport


def test_risk_score_is_bounded():
    report = RiskReport(score=0.5, level="medium", flags=[], explanation="sample")
    assert 0 <= report.score <= 1
    with pytest.raises(ValidationError):
        RiskReport(score=1.5, level="high", explanation="out of range")


def test_fit_score_is_bounded():
    report = FitReport(score=0.8)
    assert 0 <= report.score <= 1


def test_handoffs_reject_unknown_values():
    with pytest.raises(ValidationError):
        BidDecision(action="maybe", reasons=[])
    with pytest.raises(ValidationError):
        ApprovalDecision(action="send_anyway")
