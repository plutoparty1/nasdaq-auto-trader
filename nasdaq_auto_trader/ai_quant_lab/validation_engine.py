from __future__ import annotations

from math import log1p
from dataclasses import dataclass

from .audit_logger import AuditEvent, NullAuditLogger
from .backtest_engine import BacktestResult

MIN_ADVANCED_EQUITY_POINTS = 60
PBO_LIMIT = 0.35
MIN_ADVANCED_SCORE = 0.50
MIN_DEFLATED_SHARPE = 0.05


@dataclass(frozen=True, slots=True)
class ValidationResult:
    passed: bool
    promotion_eligible: bool
    metrics: dict[str, float]
    rejection_reasons: tuple[str, ...]
    missing_advanced_metrics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdvancedOverfitResult:
    metrics: dict[str, float]
    rejection_reasons: tuple[str, ...]
    missing_metrics: tuple[str, ...]
    promotion_eligible: bool


class ValidationEngine:
    def __init__(self, audit_logger: NullAuditLogger | None = None) -> None:
        self.audit_logger = audit_logger or NullAuditLogger()

    def validate(self, result: BacktestResult) -> ValidationResult:
        reasons: list[str] = []
        if not result.success:
            reasons.extend(result.rejection_reasons)
        if len(result.equity_curve) < 30:
            reasons.append("insufficient_oos_history")
        if result.metrics.get("max_drawdown", 1.0) > 0.20:
            reasons.append("max_drawdown_too_high")
        if result.metrics.get("turnover", 1.0) > 0.50:
            reasons.append("turnover_too_high")
        advanced = _advanced_overfit_result(result)
        rejection_reasons = tuple(
            dict.fromkeys([*reasons, *advanced.rejection_reasons])
        )
        validation = ValidationResult(
            passed=not reasons,
            promotion_eligible=not reasons and advanced.promotion_eligible,
            metrics={
                "oos_score": _score_positive(result.metrics.get("total_return", 0.0)),
                "regime_stability_score": 0.25,
                "execution_quality_score": 0.25,
                "parameter_sensitivity_score": 0.25,
                "slippage_sensitivity_score": 0.25,
                "transaction_cost_sensitivity_score": 0.25,
                **advanced.metrics,
            },
            rejection_reasons=rejection_reasons,
            missing_advanced_metrics=advanced.missing_metrics,
        )
        self.audit_logger.append(
            AuditEvent(
                "validation_completed",
                experiment_id=result.experiment_id,
                strategy_id=result.strategy_id,
                payload={
                    "passed": validation.passed,
                    "promotion_eligible": validation.promotion_eligible,
                    "missing_advanced_metrics": list(validation.missing_advanced_metrics),
                    "advanced_metrics": {
                        key: validation.metrics[key]
                        for key in _advanced_metric_payload_names()
                    },
                },
            )
        )
        return validation


def _advanced_overfit_result(result: BacktestResult) -> AdvancedOverfitResult:
    curve = result.equity_curve
    if len(curve) < MIN_ADVANCED_EQUITY_POINTS:
        missing = _advanced_metric_names()
        return AdvancedOverfitResult(
            metrics=_missing_advanced_metrics(),
            rejection_reasons=("advanced_overfit_evidence_insufficient",),
            missing_metrics=missing,
            promotion_eligible=False,
        )
    returns = _period_returns(curve)
    fold_returns = _fold_returns(returns, 5)
    sign_change_ratio = _sign_change_ratio(returns)
    non_positive_fold_ratio = _non_positive_ratio(fold_returns)
    pbo_probability = _bounded(
        (0.60 * non_positive_fold_ratio) + (0.40 * sign_change_ratio)
    )
    purged_score = _bounded(1.0 - pbo_probability)
    cpcv_score = _bounded(_positive_pair_ratio(fold_returns) - (0.25 * sign_change_ratio))
    deflated_sharpe = _deflated_sharpe_ratio(result, len(returns))
    multiple_penalty = _multiple_testing_penalty(result)
    reasons: list[str] = []
    if purged_score < MIN_ADVANCED_SCORE:
        reasons.append("purged_cross_validation_score_too_low")
    if cpcv_score < MIN_ADVANCED_SCORE:
        reasons.append("cpcv_score_too_low")
    if pbo_probability > PBO_LIMIT:
        reasons.append("pbo_probability_too_high")
    if deflated_sharpe < MIN_DEFLATED_SHARPE:
        reasons.append("deflated_sharpe_ratio_too_low")
    return AdvancedOverfitResult(
        metrics={
            "purged_cross_validation_score": purged_score,
            "combinatorial_purged_cross_validation_score": cpcv_score,
            "pbo_probability": pbo_probability,
            "deflated_sharpe_ratio": deflated_sharpe,
            "multiple_testing_correction_penalty": multiple_penalty,
        },
        rejection_reasons=tuple(reasons),
        missing_metrics=(),
        promotion_eligible=not reasons,
    )


def _score_positive(value: float) -> float:
    return max(min(value * 5, 1.0), 0.0)


def _advanced_metric_names() -> tuple[str, ...]:
    return (
        "purged_cross_validation",
        "combinatorial_purged_cross_validation",
        "pbo",
        "deflated_sharpe_ratio",
        "multiple_testing_correction",
    )


def _advanced_metric_payload_names() -> tuple[str, ...]:
    return (
        "purged_cross_validation_score",
        "combinatorial_purged_cross_validation_score",
        "pbo_probability",
        "deflated_sharpe_ratio",
        "multiple_testing_correction_penalty",
    )


def _missing_advanced_metrics() -> dict[str, float]:
    return {
        "purged_cross_validation_score": 0.0,
        "combinatorial_purged_cross_validation_score": 0.0,
        "pbo_probability": 1.0,
        "deflated_sharpe_ratio": 0.0,
        "multiple_testing_correction_penalty": 1.0,
    }


def _period_returns(equity_curve: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(
        (equity_curve[index] / equity_curve[index - 1]) - 1
        for index in range(1, len(equity_curve))
        if equity_curve[index - 1] > 0
    )


def _fold_returns(returns: tuple[float, ...], fold_count: int) -> tuple[float, ...]:
    fold_size = max(len(returns) // fold_count, 1)
    folds: list[float] = []
    for fold_index in range(fold_count):
        start = fold_index * fold_size
        stop = len(returns) if fold_index == fold_count - 1 else start + fold_size
        values = returns[start:stop]
        if values:
            folds.append(sum(values))
    return tuple(folds)


def _sign_change_ratio(returns: tuple[float, ...]) -> float:
    signed = tuple(value for value in returns if value != 0)
    if len(signed) < 2:
        return 0.0
    changes = sum(
        1
        for index in range(1, len(signed))
        if (signed[index] > 0) != (signed[index - 1] > 0)
    )
    return changes / (len(signed) - 1)


def _non_positive_ratio(values: tuple[float, ...]) -> float:
    if not values:
        return 1.0
    return sum(1 for value in values if value <= 0) / len(values)


def _positive_pair_ratio(values: tuple[float, ...]) -> float:
    if len(values) < 2:
        return 0.0
    total = 0
    positive = 0
    for left_index in range(len(values)):
        for right_index in range(left_index + 1, len(values)):
            total += 1
            if values[left_index] + values[right_index] > 0:
                positive += 1
    return positive / total if total else 0.0


def _deflated_sharpe_ratio(result: BacktestResult, sample_count: int) -> float:
    sharpe = result.metrics.get("sharpe", 0.0)
    trial_count = max(result.metrics.get("strategy_trial_count", 1.0), 1.0)
    sample_adjustment = sample_count / (sample_count + 25)
    trial_adjustment = 1.0 + log1p(trial_count)
    return _bounded((sharpe / (trial_adjustment**0.5)) * sample_adjustment)


def _multiple_testing_penalty(result: BacktestResult) -> float:
    trial_count = max(result.metrics.get("strategy_trial_count", 1.0), 1.0)
    return _bounded(log1p(trial_count) / 10)


def _bounded(value: float) -> float:
    return max(min(value, 1.0), 0.0)
