from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Final

from .audit_logger import AuditEvent, NullAuditLogger
from .backtest_engine import BacktestResult

ADVANCED_METRIC_NAMES: Final = (
    "purged_cross_validation",
    "combinatorial_purged_cross_validation",
    "pbo",
    "deflated_sharpe_ratio",
    "multiple_testing_correction",
)


@dataclass(frozen=True, slots=True)
class ValidationResult:
    passed: bool
    promotion_eligible: bool
    metrics: dict[str, float]
    rejection_reasons: tuple[str, ...]
    missing_advanced_metrics: tuple[str, ...]
    paper_eligible: bool = False
    evidence_scope: str = "single_backtest_in_sample"


class ValidationEngine:
    def __init__(self, audit_logger: NullAuditLogger | None = None) -> None:
        self.audit_logger = audit_logger or NullAuditLogger()

    def validate(self, result: BacktestResult) -> ValidationResult:
        """Check one simulation's quality; it supplies no independent validation evidence."""
        reasons: list[str] = []
        if not result.success:
            reasons.extend(("backtest_failed", *result.rejection_reasons))
        if len(result.equity_curve) < 30:
            reasons.append("insufficient_backtest_history")
        if any(not isfinite(value) or value <= 0 for value in result.equity_curve):
            reasons.append("invalid_equity_curve")
        if any(not isfinite(value) for value in result.metrics.values()):
            reasons.append("nonfinite_backtest_metrics")
        if result.metrics.get("max_drawdown", 1.0) > 0.20:
            reasons.append("max_drawdown_too_high")
        if result.metrics.get("turnover", 1.0) > 0.50:
            reasons.append("turnover_too_high")
        total_return = result.metrics.get("total_return", 0.0)
        advanced_metrics = {
            "purged_cross_validation_score": 0.0,
            "combinatorial_purged_cross_validation_score": 0.0,
            "pbo_probability": 1.0,
            "deflated_sharpe_ratio": 0.0,
            "multiple_testing_correction_penalty": 1.0,
        }
        # Legacy numeric fields are missing-value sentinels, never computed evidence.
        validation = ValidationResult(
            passed=not reasons,
            promotion_eligible=False,
            metrics={
                "in_sample_score": (
                    max(min(total_return * 5, 1.0), 0.0) if isfinite(total_return) else 0.0
                ),
                **advanced_metrics,
            },
            rejection_reasons=tuple(dict.fromkeys([*reasons, "independent_validation_required"])),
            missing_advanced_metrics=ADVANCED_METRIC_NAMES,
        )
        self.audit_logger.append(
            AuditEvent(
                "validation_completed",
                experiment_id=result.experiment_id,
                strategy_id=result.strategy_id,
                payload={
                    "passed": validation.passed,
                    "promotion_eligible": validation.promotion_eligible,
                    "evidence_scope": "single_backtest_in_sample",
                    "advanced_metrics_status": "missing",
                    "missing_advanced_metrics": list(validation.missing_advanced_metrics),
                    "advanced_metrics": advanced_metrics,
                },
            )
        )
        return validation
