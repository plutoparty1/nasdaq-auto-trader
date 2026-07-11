from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditEvent
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.degradation_metrics import (
    DegradationMetricEvaluation,
    LedgerScope,
    MetricState,
    evaluate_ledger_degradation,
)
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject, JsonValue

DegradationStatus = Literal["healthy", "rolled_back", "blocked"]


class AuditAppender(Protocol):
    def append(self, event: AuditEvent) -> bool: ...


@dataclass(frozen=True, slots=True)
class DegradationResult:
    status: DegradationStatus
    reasons: tuple[str, ...]
    samples: int
    rolled_back: bool
    max_drawdown_pct: float
    latest_loss_pct: float

    def to_json_object(self) -> JsonObject:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "samples": self.samples,
            "rolled_back": self.rolled_back,
            "max_drawdown_pct": self.max_drawdown_pct,
            "latest_loss_pct": self.latest_loss_pct,
        }


@dataclass(frozen=True, slots=True)
class PromotedStrategy:
    strategy_id: str
    strategy_version: str


@dataclass(frozen=True, slots=True)
class DegradationDetection:
    promoted: PromotedStrategy
    reasons: tuple[str, ...]
    evaluation: DegradationMetricEvaluation


class DegradationMonitor:
    def __init__(
        self,
        config: AIQuantConfig,
        registry: StrategyRegistry,
        audit_logger: AuditAppender,
    ) -> None:
        self.config = config
        self.registry = registry
        self.audit_logger = audit_logger

    def evaluate(self, ledger_path: str | Path) -> DegradationResult:
        promoted = _promoted_strategy(self.registry.load_promoted_strategy())
        if promoted is None:
            result = DegradationResult(
                "blocked",
                ("promoted_strategy_missing",),
                0,
                False,
                0.0,
                0.0,
            )
            self._append_blocked_audit(result)
            return result

        evaluation = evaluate_ledger_degradation(
            Path(ledger_path),
            LedgerScope(promoted.strategy_id, promoted.strategy_version),
            self.config,
        )
        if evaluation.reasons:
            return self._rollback(DegradationDetection(promoted, evaluation.reasons, evaluation))
        if not self.audit_logger.append(_checked_event(promoted, evaluation)):
            return self._rollback(
                DegradationDetection(promoted, ("audit_log_write_failed",), evaluation)
            )
        return DegradationResult(
            "healthy",
            (),
            evaluation.samples,
            False,
            evaluation.metrics.max_drawdown_pct,
            evaluation.metrics.latest_loss_pct,
        )

    def _append_blocked_audit(self, result: DegradationResult) -> None:
        self.audit_logger.append(
            AuditEvent(
                "strategy_degradation_check_blocked",
                severity="warning",
                payload=result.to_json_object(),
            )
        )

    def _rollback(
        self,
        detection: DegradationDetection,
    ) -> DegradationResult:
        self.audit_logger.append(_detected_event(detection))
        decision = self.registry.rollback_to_no_trade(detection.reasons[0])
        return DegradationResult(
            "rolled_back" if decision.allowed else "blocked",
            _merge_reasons(detection.reasons, decision.reasons),
            detection.evaluation.samples,
            decision.allowed,
            detection.evaluation.metrics.max_drawdown_pct,
            detection.evaluation.metrics.latest_loss_pct,
        )


def _promoted_strategy(promoted: JsonObject | None) -> PromotedStrategy | None:
    if promoted is None:
        return None
    strategy_id = _string(promoted.get("active_strategy_id"))
    strategy_version = _string(promoted.get("strategy_version"))
    if not strategy_id or not strategy_version:
        return None
    return PromotedStrategy(strategy_id, strategy_version)


def _checked_event(
    promoted: PromotedStrategy,
    evaluation: DegradationMetricEvaluation,
) -> AuditEvent:
    return AuditEvent(
        "strategy_degradation_checked",
        strategy_id=promoted.strategy_id,
        strategy_version=promoted.strategy_version,
        payload=_metric_payload((), evaluation.samples, evaluation.metrics),
    )


def _detected_event(detection: DegradationDetection) -> AuditEvent:
    return AuditEvent(
        "strategy_degradation_detected",
        severity="warning",
        strategy_id=detection.promoted.strategy_id,
        strategy_version=detection.promoted.strategy_version,
        payload=_metric_payload(
            detection.reasons,
            detection.evaluation.samples,
            detection.evaluation.metrics,
        ),
    )


def _metric_payload(
    reasons: tuple[str, ...],
    samples: int,
    metrics: MetricState,
) -> JsonObject:
    return {
        "reasons": list(reasons),
        "samples": samples,
        "max_drawdown_pct": metrics.max_drawdown_pct,
        "latest_loss_pct": metrics.latest_loss_pct,
    }


def _merge_reasons(primary: tuple[str, ...], secondary: tuple[str, ...]) -> tuple[str, ...]:
    reasons: list[str] = []
    for reason in (*primary, *secondary):
        if reason and reason not in reasons:
            reasons.append(reason)
    return tuple(reasons)


def _string(value: JsonValue | None) -> str:
    return value.strip() if isinstance(value, str) else ""
