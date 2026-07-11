from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from math import isfinite
from pathlib import Path
from typing import Final

from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.strategy_schema_safety import (
    NonFiniteJsonNumberError,
    parse_finite_json_float,
    reject_non_finite_json,
)
from nasdaq_auto_trader.ai_quant_lab.types import JsonValue

MAX_LEDGER_INTEGER_DIGITS: Final = 308


@dataclass(frozen=True, slots=True)
class MalformedLedgerNumber(ValueError):
    digits: int

    def __str__(self) -> str:
        return f"malformed ledger number with {self.digits} digits"


@dataclass(frozen=True, slots=True)
class LedgerScope:
    strategy_id: str
    strategy_version: str


@dataclass(frozen=True, slots=True)
class MetricState:
    max_drawdown_pct: float
    latest_loss_pct: float


@dataclass(frozen=True, slots=True)
class DegradationMetricEvaluation:
    reasons: tuple[str, ...]
    samples: int
    metrics: MetricState


@dataclass(frozen=True, slots=True)
class LedgerSample:
    strategy_id: str
    strategy_version: str
    status: str
    equity_curve: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class LedgerLoadResult:
    samples: tuple[LedgerSample, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DegradationReasonInput:
    ledger_reasons: tuple[str, ...]
    sample_count: int
    metrics: MetricState
    config: AIQuantConfig


def evaluate_ledger_degradation(
    path: Path,
    scope: LedgerScope,
    config: AIQuantConfig,
) -> DegradationMetricEvaluation:
    ledger = _load_ledger(path)
    samples = _samples_for_scope(ledger.samples, scope)
    metrics = _metric_state(samples)
    reasons = _degradation_reasons(
        DegradationReasonInput(ledger.reasons, len(samples), metrics, config)
    )
    return DegradationMetricEvaluation(reasons, len(samples), metrics)


def _load_ledger(path: Path) -> LedgerLoadResult:
    try:
        with path.open("r", encoding="utf-8") as file:
            samples: list[LedgerSample] = []
            for line in file:
                if not line.strip():
                    continue
                sample = _ledger_sample(_load_json_value(line))
                if sample is None:
                    return LedgerLoadResult(tuple(samples), ("performance_ledger_malformed",))
                samples.append(sample)
    except OSError:
        return LedgerLoadResult((), ("performance_ledger_missing",))
    except UnicodeDecodeError:
        return LedgerLoadResult((), ("performance_ledger_malformed",))
    return LedgerLoadResult(tuple(samples), ())


def _load_json_value(line: str) -> JsonValue | None:
    try:
        raw: JsonValue = json.loads(
            line,
            parse_constant=reject_non_finite_json,
            parse_float=parse_finite_json_float,
            parse_int=_parse_json_int,
        )
    except (JSONDecodeError, NonFiniteJsonNumberError, MalformedLedgerNumber):
        return None
    return raw


def _ledger_sample(value: JsonValue | None) -> LedgerSample | None:
    if not isinstance(value, dict):
        return None
    strategy_id = _string(value.get("strategy_id"))
    strategy_version = _string(value.get("strategy_version"))
    status = _string(value.get("status"))
    equity_curve = _float_tuple(value.get("equity_curve"))
    if not strategy_id or not strategy_version or not status or len(equity_curve) < 2:
        return None
    return LedgerSample(strategy_id, strategy_version, status, equity_curve)


def _samples_for_scope(
    samples: tuple[LedgerSample, ...],
    scope: LedgerScope,
) -> tuple[LedgerSample, ...]:
    return tuple(sample for sample in samples if _matches_scope(sample, scope))


def _matches_scope(sample: LedgerSample, scope: LedgerScope) -> bool:
    return (
        sample.strategy_id == scope.strategy_id
        and sample.strategy_version == scope.strategy_version
        and sample.status == "completed"
    )


def _degradation_reasons(reason_input: DegradationReasonInput) -> tuple[str, ...]:
    reasons = list(reason_input.ledger_reasons)
    if not reasons and reason_input.sample_count == 0:
        reasons.append("performance_samples_missing")
    if not reasons:
        if reason_input.metrics.max_drawdown_pct >= reason_input.config.max_strategy_drawdown_pct:
            reasons.append("strategy_drawdown_limit_exceeded")
        if reason_input.metrics.latest_loss_pct >= reason_input.config.max_daily_loss_pct:
            reasons.append("daily_loss_limit_exceeded")
    return tuple(reasons)


def _metric_state(samples: tuple[LedgerSample, ...]) -> MetricState:
    if not samples:
        return MetricState(0.0, 0.0)
    points = tuple(point for sample in samples for point in sample.equity_curve)
    latest = samples[-1].equity_curve
    return MetricState(_max_drawdown_pct(points), _loss_pct(latest[0], latest[-1]))


def _max_drawdown_pct(points: tuple[float, ...]) -> float:
    peak = points[0]
    drawdown = 0.0
    for point in points:
        if point > peak:
            peak = point
        if peak > 0:
            drawdown = max(drawdown, (peak - point) / peak)
    return drawdown


def _loss_pct(start: float, end: float) -> float:
    if end >= start:
        return 0.0
    return (start - end) / start


def _float_tuple(value: JsonValue | None) -> tuple[float, ...]:
    if not isinstance(value, list):
        return ()
    numbers: list[float] = []
    for item in value:
        number = _positive_finite_float(item)
        if number is None:
            return ()
        numbers.append(number)
    return tuple(numbers)


def _parse_json_int(token: str) -> int:
    digits = len(token.removeprefix("-"))
    if digits > MAX_LEDGER_INTEGER_DIGITS:
        raise MalformedLedgerNumber(digits) from None
    return int(token)


def _positive_finite_float(value: JsonValue | None) -> float | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    if not isfinite(number) or number <= 0:
        return None
    return number


def _string(value: JsonValue | None) -> str:
    return value.strip() if isinstance(value, str) else ""
