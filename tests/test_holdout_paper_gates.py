from dataclasses import replace

import pytest

from nasdaq_auto_trader.ai_quant_lab.scoring_engine import ScoringEngine
from nasdaq_auto_trader.ai_quant_lab.validation_engine import ValidationEngine
from tests.test_validation_evidence_contract import profitable_backtest


def test_temporal_screen_allows_paper_without_claiming_advanced_evidence() -> None:
    backtest = profitable_backtest()
    basic = ValidationEngine().validate(backtest)
    screened = replace(
        basic, paper_eligible=True, evidence_scope="fixed_rule_temporal_holdout",
        rejection_reasons=(),
    )

    score = ScoringEngine().score(backtest, screened)

    assert not score.rejection_reasons
    assert not score.promotion_recommendation
    assert screened.missing_advanced_metrics == basic.missing_advanced_metrics
    assert not screened.promotion_eligible


@pytest.mark.parametrize("scope", ["single_backtest_in_sample", "unknown"])
def test_paper_flag_without_temporal_scope_stays_blocked(scope: str) -> None:
    backtest = profitable_backtest()
    screened = replace(
        ValidationEngine().validate(backtest), paper_eligible=True,
        evidence_scope=scope, rejection_reasons=(),
    )

    score = ScoringEngine().score(backtest, screened)

    assert "independent_validation_required" in score.rejection_reasons
    assert "overfit_metrics_missing" in score.rejection_reasons
    assert not score.promotion_recommendation


def test_temporal_scope_cannot_claim_advanced_promotion_with_inconsistent_flags() -> None:
    backtest = profitable_backtest()
    screened = replace(
        ValidationEngine().validate(backtest), paper_eligible=True,
        evidence_scope="fixed_rule_temporal_holdout", promotion_eligible=True,
        rejection_reasons=(), missing_advanced_metrics=(),
    )

    score = ScoringEngine().score(backtest, screened)

    assert not score.promotion_recommendation
