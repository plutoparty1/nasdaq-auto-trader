from dataclasses import replace
from math import isfinite

import pytest

from nasdaq_auto_trader.ai_quant_lab.backtest_engine import BacktestResult
from nasdaq_auto_trader.ai_quant_lab.scoring_engine import ScoringEngine
from nasdaq_auto_trader.ai_quant_lab.validation_engine import ValidationEngine, ValidationResult


def profitable_backtest() -> BacktestResult:
    return BacktestResult(
        experiment_id="single-curve",
        strategy_id="research-candidate",
        success=True,
        metrics={
            "total_return": 1.0,
            "cagr": 0.4,
            "sharpe": 3.0,
            "sortino": 4.0,
            "max_drawdown": 0.02,
            "profit_factor": 3.0,
            "turnover": 0.1,
        },
        trades=(),
        equity_curve=tuple(100_000.0 + index * 100 for index in range(1001)),
    )


def test_basic_checks_pass_without_claiming_independent_validation() -> None:
    # Given: a long profitable curve without any holdout or fitted-fold results.
    backtest = profitable_backtest()
    # When
    validation = ValidationEngine().validate(backtest)
    # Then: research remains useful, but its return is explicitly in sample.
    assert validation.passed
    assert not validation.promotion_eligible
    assert "independent_validation_required" in validation.rejection_reasons
    assert validation.metrics["in_sample_score"] == 1.0
    assert "oos_score" not in validation.metrics
    assert set(validation.missing_advanced_metrics) == {
        "purged_cross_validation",
        "combinatorial_purged_cross_validation",
        "pbo",
        "deflated_sharpe_ratio",
        "multiple_testing_correction",
    }


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1.0, 0.0])
def test_basic_checks_reject_invalid_equity(invalid: float) -> None:
    # Given
    backtest = profitable_backtest()
    backtest = replace(backtest, equity_curve=(*backtest.equity_curve[:-1], invalid))
    # When
    validation = ValidationEngine().validate(backtest)
    # Then
    assert not validation.passed
    assert "invalid_equity_curve" in validation.rejection_reasons
    assert not validation.promotion_eligible


@pytest.mark.parametrize("name", ["total_return", "max_drawdown", "turnover", "sharpe"])
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_basic_checks_reject_nonfinite_metrics(name: str, invalid: float) -> None:
    # Given
    backtest = profitable_backtest()
    backtest = replace(backtest, metrics={**backtest.metrics, name: invalid})
    # When
    validation = ValidationEngine().validate(backtest)
    # Then
    assert not validation.passed
    assert "nonfinite_backtest_metrics" in validation.rejection_reasons
    assert all(isfinite(value) for value in validation.metrics.values())


def test_failed_backtest_without_reasons_cannot_pass_basic_checks() -> None:
    # Given
    backtest = replace(profitable_backtest(), success=False)
    # When
    validation = ValidationEngine().validate(backtest)
    # Then
    assert not validation.passed
    assert "backtest_failed" in validation.rejection_reasons


@pytest.mark.parametrize("passed, eligible", [(True, False), (False, True)])
def test_scoring_respects_validation_flags_even_without_reason_strings(
    passed: bool, eligible: bool,
) -> None:
    # Given: inconsistent older producer output must still fail closed.
    validation = ValidationResult(passed, eligible, {"oos_score": 1.0}, (), ())
    # When
    score = ScoringEngine().score(profitable_backtest(), validation)
    # Then
    assert not score.promotion_recommendation
    assert score.rejection_reasons


def test_scoring_retains_research_ranking_without_invented_quality_metrics() -> None:
    # Given
    backtest = profitable_backtest()
    validation = ValidationEngine().validate(backtest)
    # When
    score = ScoringEngine().score(backtest, validation)
    # Then
    assert score.final_score > 0
    assert not score.promotion_recommendation
    assert "independent_validation_required" in score.rejection_reasons
    assert "in_sample_score" in score.metrics
    assert not {
        "oos_score", "regime_stability_score", "execution_quality_score",
        "complexity_penalty", "concentration_penalty", "data_quality_penalty",
        "overfitting_penalty",
    }.intersection(score.metrics)


def test_scoring_rejects_nonfinite_input_with_finite_rank() -> None:
    # Given
    backtest = profitable_backtest()
    backtest = replace(backtest, metrics={**backtest.metrics, "sharpe": float("nan")})
    validation = ValidationEngine().validate(backtest)
    # When
    score = ScoringEngine().score(backtest, validation)
    # Then
    assert isfinite(score.final_score)
    assert not score.promotion_recommendation
    assert "nonfinite_backtest_metrics" in score.rejection_reasons
