from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from math import isfinite
from types import MappingProxyType
from typing import Final

from nasdaq_auto_trader.learning_strategy_template import candidate_payload
from nasdaq_auto_trader.quant_data.feature_statistics import normalized_timestamps

from .backtest_engine import BacktestEngine, BacktestRequest, BacktestResult
from .backtest_market_data import validate_backtest_market_data
from .backtest_metrics import MetricTiming, calculate_backtest_metrics
from .config import AIQuantConfig
from .operator_market_data import BarsBySymbol
from .strategy_schema import StrategySpec
from .strategy_schema_validation import parse_strategy_spec_json
from .types import JsonObject
from .validation_engine import ADVANCED_METRIC_NAMES

HOLDOUT_PROTOCOL_VERSION: Final = "fixed-rule-holdout-v1"
MIN_TRAIN_BARS: Final = 60
EMBARGO_BARS: Final = 60
WARMUP_BARS: Final = 60
MIN_TEST_BARS: Final = 126
MIN_CLOSED_TRADES: Final = 3
INITIAL_CASH: Final = 100_000.0


@dataclass(frozen=True, slots=True)
class HoldoutEvidence:
    """Historical fixed-rule screening only, with no statistical or live eligibility claim."""

    passed: bool
    reasons: tuple[str, ...]
    metrics: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))
    train_start: str = ""
    train_end: str = ""
    test_start: str = ""
    test_end: str = ""
    train_bars: int = 0
    test_bars: int = 0
    embargo_bars: int = EMBARGO_BARS
    warmup_bars: int = WARMUP_BARS
    protocol_version: str = HOLDOUT_PROTOCOL_VERSION
    backtest: BacktestResult | None = None

    def to_json_object(self) -> JsonObject:
        return {
            "protocol_version": self.protocol_version,
            "evidence_scope": "fixed_rule_chronological_holdout_screen",
            "passed": self.passed,
            "rejection_reasons": list(self.reasons),
            "metrics": {key: value for key, value in self.metrics.items()},
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "train_bars": self.train_bars,
            "test_bars": self.test_bars,
            "embargo_bars": self.embargo_bars,
            "warmup_bars": self.warmup_bars,
            "parameter_fitting_performed": False,
            "statistical_significance_claimed": False,
            "missing_advanced_metrics": list(ADVANCED_METRIC_NAMES),
            "promoted_to_live": False,
        }


def evaluate_fixed_rule_holdout(
    spec: StrategySpec,
    bars_by_symbol: BarsBySymbol,
    config: AIQuantConfig,
) -> HoldoutEvidence:
    """Reserve disjoint development, embargo, warmup and test periods; never fit parameters."""
    count, data_reason = validate_backtest_market_data(bars_by_symbol, INITIAL_CASH)
    if data_reason is not None:
        return HoldoutEvidence(False, (data_reason,))
    if not _is_fixed_rule(spec, bars_by_symbol):
        return HoldoutEvidence(False, ("holdout_fixed_rule_unsupported",))
    if not all(isfinite(cost) and 0 <= cost < 10_000 for cost in (
        config.commission_bps, config.slippage_bps,
    )) or config.commission_bps + config.slippage_bps >= 10_000:
        return HoldoutEvidence(False, ("holdout_cost_assumptions_invalid",))
    if config.min_oos_months < 1 or not (
        isfinite(config.max_strategy_drawdown_pct) and 0 < config.max_strategy_drawdown_pct <= 1
    ):
        return HoldoutEvidence(False, ("holdout_config_invalid",))
    test_count = max(MIN_TEST_BARS, config.min_oos_months * 21)
    required = MIN_TRAIN_BARS + EMBARGO_BARS + WARMUP_BARS + test_count
    if count < required:
        return HoldoutEvidence(False, ("holdout_history_insufficient",), MappingProxyType({
            "available_bars": float(count), "required_bars": float(required),
        }))
    train_count = count - EMBARGO_BARS - WARMUP_BARS - test_count
    warmup_start = train_count + EMBARGO_BARS
    test_start = warmup_start + WARMUP_BARS
    reference = next(iter(bars_by_symbol.values()))
    simulated = BacktestEngine(config).run(BacktestRequest(
        spec,
        {symbol: bars[warmup_start:] for symbol, bars in bars_by_symbol.items()},
        initial_cash=INITIAL_CASH,
        trade_start_index=WARMUP_BARS - 1,
    ))
    bounds = HoldoutEvidence(
        False, simulated.rejection_reasons,
        train_start=reference[0].timestamp, train_end=reference[train_count - 1].timestamp,
        test_start=reference[test_start].timestamp, test_end=reference[-1].timestamp,
        train_bars=train_count, test_bars=test_count,
    )
    if not simulated.success:
        return replace(bounds, reasons=("holdout_backtest_failed", *simulated.rejection_reasons))
    equity = simulated.equity_curve[WARMUP_BARS - 1:]
    timestamps = normalized_timestamps(reference[test_start - 1:])
    if timestamps is None or len(equity) != test_count + 1 or any(
        not isfinite(value) or value <= 0 for value in equity
    ):
        return replace(bounds, reasons=("holdout_evidence_invalid",))
    metrics = calculate_backtest_metrics(
        equity, simulated.trades, MetricTiming(timestamps, 252.0),
    ).to_mapping()
    scored = replace(simulated, equity_curve=equity, metrics=metrics)
    reasons = _screen_reasons(scored, config)
    return replace(
        bounds, passed=not reasons, reasons=reasons,
        metrics=MappingProxyType(dict(metrics)), backtest=scored,
    )


def _is_fixed_rule(spec: StrategySpec, bars: BarsBySymbol) -> bool:
    expected_payload = candidate_payload(bars)
    parsed = parse_strategy_spec_json(json.dumps(expected_payload))
    expected = parsed.spec
    if expected is None:
        return False
    ignored = {"version", "metadata", "description"}
    if {key: value for key, value in spec.raw.items() if key not in ignored} != {
        key: value for key, value in expected_payload.items() if key not in ignored
    }:
        return False
    return replace(
        spec, version=expected.version, created_at=expected.created_at,
        raw=expected.raw, description=expected.description,
    ) == expected


def _screen_reasons(result: BacktestResult, config: AIQuantConfig) -> tuple[str, ...]:
    metrics = result.metrics
    if any(not isfinite(value) for value in metrics.values()):
        return ("holdout_evidence_invalid",)
    reasons: list[str] = []
    if metrics["trade_count"] < MIN_CLOSED_TRADES:
        reasons.append("holdout_closed_trades_insufficient")
    if metrics["total_return"] <= 0:
        reasons.append("holdout_return_not_positive")
    if metrics["annualization_available"] != 1 or metrics["sharpe"] <= 0:
        reasons.append("holdout_risk_adjusted_return_not_positive")
    if metrics["profit_factor_available"] != 1:
        reasons.append("holdout_profit_factor_unavailable")
    elif metrics["profit_factor"] <= 1:
        reasons.append("holdout_profit_factor_too_low")
    if metrics["max_drawdown"] > min(0.20, config.max_strategy_drawdown_pct):
        reasons.append("holdout_drawdown_too_high")
    if metrics["turnover"] > 0.50:
        reasons.append("holdout_turnover_too_high")
    return tuple(reasons)
