from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from nasdaq_auto_trader.entry_policy_experiment import EntryPolicyStrategy
from nasdaq_auto_trader.models import Bar, Position
from nasdaq_auto_trader.strategy_config import StrategyConfig


def shared_config() -> StrategyConfig:
    return StrategyConfig(sma_fast=5, sma_slow=20, ema_fast=5, ema_slow=20,
                          long_sma=20, stop_loss_pct=.03, take_profit_pct=.05)


def history(*, falling: bool = False, conflict: bool = False) -> list[Bar]:
    start = datetime(2025, 1, 1, 21, tzinfo=timezone.utc)
    prices = [100 + index * (-.1 if falling else .1) for index in range(220)]
    if conflict:
        prices[-1] += 1
    return [Bar("TEST", (start + timedelta(days=index)).isoformat(), price,
                price + .1, price - .1, price, 100 + index)
            for index, price in enumerate(prices)]


def test_c_blocks_actual_simultaneous_buy_sell_scores() -> None:
    # Given the real technical indicators produce simultaneous qualifying scores.
    data = history(conflict=True)
    baseline = EntryPolicyStrategy(shared_config(), "B")
    corrected = EntryPolicyStrategy(shared_config(), "C")
    assert baseline.decide("TEST", data, None).action == "buy"
    # When C evaluates exactly the same completed history while flat.
    result = corrected.decide("TEST", data, None)
    # Then a qualifying general sell signal vetoes this entry.
    assert result.action == "hold"
    assert result.reasons[-1] == "conflicting_entry_exit_signal"


@pytest.mark.parametrize("policy", ["B", "C"])
def test_zero_buys_and_low_score_are_valid_no_trade(policy: str) -> None:
    strategy = EntryPolicyStrategy(shared_config(), policy)
    data = history(falling=True)
    result = strategy.decide("TEST", data, None)
    assert result.action == "hold"
    assert strategy.records[-1].buy_score == 0
    assert strategy.records[-1].no_trade
    assert strategy.filled_buy_sessions == frozenset()


def test_a_reproduces_low_score_minimum_then_next_five_minute_general_sell() -> None:
    strategy = EntryPolicyStrategy(shared_config(), "A")
    data = history(falling=True)
    timestamp = datetime.fromisoformat(data[-1].timestamp)
    buy = strategy.evaluate("TEST", data, None, evaluation_timestamp=timestamp.isoformat())
    held = Position("TEST", 1, data[-1].close, data[-1].close)
    sell = strategy.evaluate("TEST", data, held,
                             evaluation_timestamp=(timestamp + timedelta(minutes=5)).isoformat())
    assert (buy.action, buy.score, sell.action) == ("buy", 0, "sell")
    assert "daily_minimum_best_affordable" in buy.reasons
    assert sell.score >= shared_config().sell_score and sell.score < 88
    assert strategy.records[0].data_fingerprint == strategy.records[1].data_fingerprint
    assert strategy.records[0].sell_score == sell.score


def test_c_repeated_bar_never_reenters_even_after_fill_and_exit() -> None:
    strategy = EntryPolicyStrategy(replace(shared_config(), sell_score=99), "C")
    data = history()
    first = strategy.decide("TEST", data, None)
    strategy.register_entry_fill("TEST", first.latest_price, 1, data[-1].timestamp)
    strategy.register_exit_fill("TEST", 0)
    repeated = strategy.decide("TEST", data, None)
    assert first.action == "buy"
    assert repeated.action == "hold"
    assert repeated.reasons[-1] == "completed_bar_already_evaluated"
    assert strategy.records[-1].duplicate_general_evaluation


def test_c_revised_same_bar_does_not_create_new_entry_signal() -> None:
    strategy = EntryPolicyStrategy(replace(shared_config(), sell_score=99), "C")
    data = history()
    strategy.decide("TEST", data, None)
    revised = [*data[:-1], replace(data[-1], close=data[-1].close + .01)]
    result = strategy.decide("TEST", revised, None)
    assert result.action == "hold"
    assert strategy.records[-1].data_fingerprint != strategy.records[0].data_fingerprint


def test_c_new_completed_bar_releases_signal_gate() -> None:
    strategy = EntryPolicyStrategy(replace(shared_config(), sell_score=99), "C")
    data = history()
    strategy.decide("TEST", data, None)
    following = replace(data[-1], timestamp="2025-08-09T21:00:00+00:00")
    result = strategy.decide("TEST", [*data, following], None)
    assert result.action == "buy"


def test_c_old_bar_cannot_reset_signal_gate() -> None:
    strategy = EntryPolicyStrategy(replace(shared_config(), sell_score=99), "C")
    data = history()
    strategy.decide("TEST", data, None)
    old = strategy.decide("TEST", data[:-1], None)
    repeat = strategy.decide("TEST", data, None)
    assert old.action == repeat.action == "hold"


def test_c_same_bar_new_mark_preserves_immediate_hard_stop() -> None:
    strategy = EntryPolicyStrategy(replace(shared_config(), sell_score=99), "C")
    data = history()
    buy = strategy.decide("TEST", data, None)
    held = Position("TEST", 1, buy.latest_price * .96, buy.latest_price)
    result = strategy.evaluate("TEST", data, held,
                               evaluation_timestamp="2025-08-08T21:05:00+00:00")
    assert result.action == "sell"
    assert result.reasons == ["fixed_stop_loss"]
    assert result.latest_price == pytest.approx(buy.latest_price * .96)
    assert strategy.records[-1].protective_evaluation


def test_minimum_submission_is_not_fill_and_expiry_allows_retry() -> None:
    strategy = EntryPolicyStrategy(shared_config(), "A")
    data = history(falling=True)
    first = strategy.decide("TEST", data, None)
    strategy.register_order_accepted("TEST", data[-1].timestamp)
    same_cycle = strategy.decide("TEST", data, None)
    retry = strategy.evaluate("TEST", data, None,
                              evaluation_timestamp="2025-08-08T21:05:00+00:00")
    assert first.action == retry.action == "buy"
    assert same_cycle.action == "hold"
    assert strategy.filled_buy_sessions == frozenset()


def test_actual_entry_fill_satisfies_minimum_without_reserving_future_session() -> None:
    strategy = EntryPolicyStrategy(shared_config(), "A")
    data = history(falling=True)
    strategy.decide("TEST", data, None)
    strategy.register_entry_fill("TEST", data[-1].close, 1, data[-1].timestamp)
    strategy.register_exit_fill("TEST", 0)
    after_fill = strategy.decide("TEST", data, None)
    next_session = strategy.evaluate("TEST", data, None,
                                     evaluation_timestamp="2025-08-09T21:00:00+00:00")
    assert after_fill.action == "hold"
    assert next_session.action == "buy"


@pytest.mark.parametrize("policy", ["A", "B", "C"])
def test_all_policies_keep_identical_protective_exit_and_risk(policy: str) -> None:
    strategy = EntryPolicyStrategy(shared_config(), policy)
    data = history()
    held = Position("TEST", 1, 96, 100)
    result = strategy.decide("TEST", data, held)
    assert result.reasons == ["fixed_stop_loss"]
    assert strategy.config == shared_config()
    assert strategy.config.corrected_exits is False


def test_invalid_policy_rejected() -> None:
    with pytest.raises(ValueError, match="policy"):
        EntryPolicyStrategy(shared_config(), "D")


def test_c_future_or_incomplete_daily_bar_cannot_enter() -> None:
    strategy = EntryPolicyStrategy(replace(shared_config(), sell_score=99), "C")
    data = history()
    future = strategy.evaluate("TEST", data, None,
                               evaluation_timestamp="2025-08-08T20:00:00+00:00")
    date_only = strategy.decide("TEST", [*data[:-1], replace(data[-1], timestamp="2025-08-08")], None)
    assert future.action == date_only.action == "hold"
    assert future.reasons[-1] == date_only.reasons[-1] == "completed_bar_unavailable_or_future"


def test_future_general_bar_does_not_disable_current_mark_protection() -> None:
    strategy = EntryPolicyStrategy(shared_config(), "C")
    data = history()
    result = strategy.evaluate("TEST", data, Position("TEST", 1, 96, 100),
                               evaluation_timestamp="2025-08-08T20:00:00+00:00")
    assert result.reasons == ["fixed_stop_loss"]


def test_date_only_data_requires_explicit_actual_completed_identity() -> None:
    strategy = EntryPolicyStrategy(replace(shared_config(), sell_score=99), "C")
    data = history()
    data[-1] = replace(data[-1], timestamp="2025-08-08")
    result = strategy.evaluate("TEST", data, None,
                               evaluation_timestamp="2025-08-08T21:05:00+00:00",
                               completed_bar_id="2025-08-08T21:00:00+00:00")
    assert result.action == "buy"


def test_future_atr_bars_cannot_manufacture_protection() -> None:
    strategy = EntryPolicyStrategy(shared_config(), "C")
    data = history()
    result = strategy.evaluate("TEST", data, Position("TEST", 1, 99, 100),
                               evaluation_timestamp="2024-12-31T21:00:00+00:00")
    assert result.action == "hold"
    assert result.reasons[-1] == "completed_bar_unavailable_or_future"


def test_no_completed_history_still_retains_valid_mark_hard_stop() -> None:
    strategy = EntryPolicyStrategy(shared_config(), "C")
    result = strategy.evaluate("TEST", history(), Position("TEST", 1, 96, 100),
                               evaluation_timestamp="2024-12-31T21:00:00+00:00")
    assert result.reasons == ["fixed_stop_loss"]
