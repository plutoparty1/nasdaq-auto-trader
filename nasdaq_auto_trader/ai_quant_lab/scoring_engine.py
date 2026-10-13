from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .audit_logger import AuditEvent, NullAuditLogger
from .backtest_engine import BacktestResult
from .validation_engine import ValidationResult


@dataclass(frozen=True, slots=True)
class StrategyScore:
    final_score: float
    metrics: dict[str, float]
    rejection_reasons: tuple[str, ...]
    promotion_recommendation: bool


class ScoringEngine:
    def __init__(self, audit_logger: NullAuditLogger | None = None) -> None:
        self.audit_logger = audit_logger or NullAuditLogger()

    def score(
        self,
        backtest: BacktestResult,
        validation: ValidationResult,
        champion_metrics: dict[str, float] | None = None,
    ) -> StrategyScore:
        champion = champion_metrics or {}
        metrics = _scoring_metrics(backtest, validation, champion)
        final_score = (
            0.25 * metrics["in_sample_score"]
            + 0.20 * metrics["risk_adjusted_return_score"]
            + 0.15 * metrics["profit_factor_score"]
            + 0.10 * metrics["champion_improvement_score"]
            - 0.10 * metrics["max_drawdown_penalty"]
            - 0.10 * metrics["turnover_slippage_penalty"]
        )
        rejection_reasons = _rejection_reasons(backtest, validation, metrics)
        score = StrategyScore(
            final_score=final_score,
            metrics={**metrics, "final_score": final_score},
            rejection_reasons=rejection_reasons,
            promotion_recommendation=(
                validation.promotion_eligible
                and validation.evidence_scope != "fixed_rule_temporal_holdout"
                and not validation.paper_eligible
                and not validation.missing_advanced_metrics
                and not rejection_reasons and final_score > 0.65
            ),
        )
        self.audit_logger.append(
            AuditEvent(
                "scoring_completed",
                experiment_id=backtest.experiment_id,
                strategy_id=backtest.strategy_id,
                payload={"final_score": final_score, "promotion": score.promotion_recommendation},
            )
        )
        return score


def _scoring_metrics(
    backtest: BacktestResult,
    validation: ValidationResult,
    champion: dict[str, float],
) -> dict[str, float]:
    raw = backtest.metrics
    champion_return = champion.get("total_return", 0.0)
    return {
        "cagr": raw.get("cagr", 0.0),
        "sharpe": raw.get("sharpe", 0.0),
        "sortino": raw.get("sortino", 0.0),
        "calmar": raw.get("calmar", 0.0),
        "annualization_available": raw.get("annualization_available", 0.0),
        "max_drawdown": raw.get("max_drawdown", 1.0),
        "win_rate": raw.get("win_rate", 0.0),
        "profit_factor": raw.get("profit_factor", 0.0),
        "profit_factor_available": raw.get("profit_factor_available", 0.0),
        "expectancy": raw.get("expectancy", 0.0),
        "turnover": raw.get("turnover", 1.0),
        "in_sample_score": _bounded(validation.metrics.get("in_sample_score", 0.0)),
        "risk_adjusted_return_score": _bounded(raw.get("sharpe", 0.0) / 2),
        "profit_factor_score": _bounded(raw.get("profit_factor", 0.0) / 2),
        "champion_improvement_score": _bounded(raw.get("total_return", 0.0) - champion_return),
        "max_drawdown_penalty": _bounded(raw.get("max_drawdown", 1.0)),
        "turnover_slippage_penalty": _bounded(raw.get("turnover", 1.0)),
    }


def _rejection_reasons(
    backtest: BacktestResult,
    validation: ValidationResult,
    metrics: dict[str, float],
) -> tuple[str, ...]:
    reasons = list(validation.rejection_reasons)
    if not backtest.success:
        reasons.append("backtest_failed")
    if not validation.passed:
        reasons.append("validation_failed")
    paper_screen = (
        validation.passed and validation.paper_eligible
        and validation.evidence_scope == "fixed_rule_temporal_holdout"
    )
    if not validation.promotion_eligible and not paper_screen:
        reasons.append("independent_validation_required")
    if any(not isfinite(value) for value in backtest.metrics.values()):
        reasons.append("nonfinite_backtest_metrics")
    if metrics["profit_factor"] <= 0:
        reasons.append("profit_factor_missing")
    if validation.missing_advanced_metrics and not paper_screen:
        reasons.append("overfit_metrics_missing")
    return tuple(dict.fromkeys(reasons))


def _bounded(value: float) -> float:
    return max(min(value, 1.0), 0.0) if isfinite(value) else 0.0
