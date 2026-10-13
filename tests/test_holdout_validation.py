from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import sin

import pytest

from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.holdout_validation import (
    evaluate_fixed_rule_holdout,
)
from nasdaq_auto_trader.ai_quant_lab.operator_market_data import BarsBySymbol
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import StrategySpec
from nasdaq_auto_trader.ai_quant_lab.strategy_schema_validation import (
    parse_strategy_spec_json,
)
from nasdaq_auto_trader.learning_strategy_template import candidate_payload
from nasdaq_auto_trader.quant_data.features import PriceBar


def _bars(count: int = 320, trend: float = 0.15) -> BarsBySymbol:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    result: list[PriceBar] = []
    day = start
    while len(result) < count:
        if day.weekday() < 5:
            index = len(result)
            price = 100 + trend * index + 2 * sin(index / 3)
            result.append(PriceBar("QQQ", day.isoformat(), price, price + 1, price - 1,
                                   price, 1_000_000, price - 0.01, price + 0.01))
        day += timedelta(days=1)
    return {"QQQ": result}


def _spec(bars: BarsBySymbol) -> StrategySpec:
    result = parse_strategy_spec_json(json.dumps(candidate_payload(bars)))
    assert result.spec is not None
    return result.spec


def test_holdout_blocks_insufficient_history() -> None:
    # Given: one fewer bar than the disjoint development/gap/warmup/test protocol.
    bars = _bars(305)
    # When
    evidence = evaluate_fixed_rule_holdout(_spec(bars), bars, AIQuantConfig())
    # Then
    assert not evidence.passed
    assert "holdout_history_insufficient" in evidence.reasons
    assert evidence.backtest is None


def test_holdout_honors_stricter_configured_duration() -> None:
    # Given
    bars = _bars()
    # When
    evidence = evaluate_fixed_rule_holdout(_spec(bars), bars, AIQuantConfig(min_oos_months=12))
    # Then
    assert "holdout_history_insufficient" in evidence.reasons
    assert evidence.metrics["required_bars"] == 432


def test_holdout_resets_portfolio_before_test_and_excludes_warmup() -> None:
    # Given
    bars = _bars()
    # When
    evidence = evaluate_fixed_rule_holdout(_spec(bars), bars, AIQuantConfig())
    # Then
    assert evidence.backtest is not None
    assert evidence.train_bars == 74
    assert evidence.embargo_bars == evidence.warmup_bars == 60
    assert evidence.test_bars == 126
    assert len(evidence.backtest.equity_curve) == 127
    assert evidence.backtest.equity_curve[0] == 100_000
    assert all(trade.timestamp >= evidence.test_start for trade in evidence.backtest.trades)
    assert evidence.train_end < evidence.test_start
    assert evidence.backtest.metrics["annualization_available"] == 1


def test_holdout_rejects_changed_fixed_rule_even_with_unchanged_raw_payload() -> None:
    # Given: dataclass and raw payload disagree on a material strategy parameter.
    bars = _bars()
    spec = _spec(bars)
    spec = replace(spec, entry_rule=replace(spec.entry_rule, threshold=0.1))
    # When
    evidence = evaluate_fixed_rule_holdout(spec, bars, AIQuantConfig())
    # Then
    assert "holdout_fixed_rule_unsupported" in evidence.reasons
    assert evidence.backtest is None


@pytest.mark.parametrize("cost", [-1.0, float("nan"), float("inf")])
def test_holdout_rejects_invalid_cost_assumptions(cost: float) -> None:
    # Given
    bars = _bars()
    # When
    evidence = evaluate_fixed_rule_holdout(_spec(bars), bars, AIQuantConfig(commission_bps=cost))
    # Then
    assert "holdout_cost_assumptions_invalid" in evidence.reasons
    assert evidence.backtest is None


def test_holdout_does_not_claim_uncomputed_advanced_metrics() -> None:
    # Given
    bars = _bars()
    # When
    payload = evaluate_fixed_rule_holdout(_spec(bars), bars, AIQuantConfig()).to_json_object()
    # Then
    assert payload["evidence_scope"] == "fixed_rule_chronological_holdout_screen"
    assert payload["statistical_significance_claimed"] is False
    assert payload["promoted_to_live"] is False
    assert payload["missing_advanced_metrics"]


def test_holdout_no_trades_cannot_pass() -> None:
    # Given: a declining series that supplies no long trend entries.
    bars = _bars(trend=-0.15)
    # When
    evidence = evaluate_fixed_rule_holdout(_spec(bars), bars, AIQuantConfig())
    # Then
    assert not evidence.passed
    assert "holdout_closed_trades_insufficient" in evidence.reasons


def test_positive_fixed_rule_can_pass_historical_screen() -> None:
    # Given: an oscillating trend with both profitable and losing closed trades.
    bars = _bars()
    # When
    evidence = evaluate_fixed_rule_holdout(_spec(bars), bars, AIQuantConfig())
    # Then
    assert evidence.passed
    assert evidence.reasons == ()
    assert evidence.metrics["trade_count"] >= 3
    assert evidence.metrics["profit_factor_available"] == 1
    assert evidence.metrics["profit_factor"] > 1


def test_development_data_cannot_change_fixed_rule_holdout_results() -> None:
    # Given: only development and embargo bars change, with unchanged evaluation inputs.
    original = _bars()
    changed = {"QQQ": [
        replace(bar, open=200, high=201, low=199, close=200) if index < 134 else bar
        for index, bar in enumerate(original["QQQ"])
    ]}
    expected = evaluate_fixed_rule_holdout(_spec(original), original, AIQuantConfig())
    # When
    actual = evaluate_fixed_rule_holdout(_spec(changed), changed, AIQuantConfig())
    # Then
    assert actual.metrics == expected.metrics
    assert actual.backtest is not None and expected.backtest is not None
    assert actual.backtest.trades == expected.backtest.trades
    assert actual.backtest.equity_curve == expected.backtest.equity_curve


def test_holdout_honors_configured_drawdown_limit() -> None:
    # Given
    bars = _bars()
    # When
    evidence = evaluate_fixed_rule_holdout(
        _spec(bars), bars, AIQuantConfig(max_strategy_drawdown_pct=0.00001),
    )
    # Then
    assert not evidence.passed
    assert "holdout_drawdown_too_high" in evidence.reasons


def test_holdout_includes_transaction_costs() -> None:
    # Given
    bars = _bars()
    normal = evaluate_fixed_rule_holdout(_spec(bars), bars, AIQuantConfig())
    # When
    costly = evaluate_fixed_rule_holdout(_spec(bars), bars, AIQuantConfig(commission_bps=500))
    # Then
    assert costly.metrics["total_return"] < normal.metrics["total_return"]
    assert not costly.passed


def test_repeated_identical_screen_does_not_change_result() -> None:
    # Given
    bars = _bars()
    spec = _spec(bars)
    first = evaluate_fixed_rule_holdout(spec, bars, AIQuantConfig())
    # When
    repeated = evaluate_fixed_rule_holdout(spec, bars, AIQuantConfig())
    # Then
    assert repeated.to_json_object() == first.to_json_object()


def test_holdout_rejects_misaligned_market_data() -> None:
    # Given
    bars = _bars()
    bars["AAPL"] = [replace(bar, symbol="AAPL") for bar in bars["QQQ"][:-1]]
    # When
    evidence = evaluate_fixed_rule_holdout(_spec(bars), bars, AIQuantConfig())
    # Then
    assert not evidence.passed
    assert "market_data_timestamps_misaligned" in evidence.reasons
