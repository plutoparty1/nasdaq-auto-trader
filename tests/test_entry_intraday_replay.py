from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nasdaq_auto_trader.backtest import Backtester
from nasdaq_auto_trader.backtest_costs import BacktestCosts
from nasdaq_auto_trader.entry_comparison_risk import MatchedEntryRisk
from nasdaq_auto_trader.entry_intraday_replay import (
    IntradayEvaluation,
    ReplaySession,
    filter_completed_intraday,
    run_intraday_replay,
)
from nasdaq_auto_trader.entry_policy_experiment import EntryPolicyStrategy
from nasdaq_auto_trader.exit_experiment_config import CostScenario, ExperimentInputError
from nasdaq_auto_trader.models import Bar, Position
from nasdaq_auto_trader.strategy_config import StrategyConfig


def daily_history() -> list[Bar]:
    start = datetime(2025, 1, 1, 21, tzinfo=timezone.utc)
    return [Bar("TEST", (start + timedelta(days=index)).isoformat(),
                10 - index * .002, 10.01 - index * .002,
                9.99 - index * .002, 10 - index * .002, 1000)
            for index in range(220)]


def config() -> StrategyConfig:
    return StrategyConfig(sma_fast=5, sma_slow=20, ema_fast=5, ema_slow=20,
                          long_sma=20, stop_loss_pct=.03, take_profit_pct=.05)


def minutes() -> list[Bar]:
    return [Bar("TEST", f"2025-08-11T13:{minute}:00+00:00", 10, 10.01, 9.99, 10, 100)
            for minute in (35, 40, 45, 50)]


def session() -> ReplaySession:
    return ReplaySession("2025-08-11T13:30:00+00:00", "2025-08-11T20:00:00+00:00")


def test_prior_daily_history_excludes_same_session_and_future() -> None:
    data = daily_history()
    contaminated = [*data, replace(data[-1], timestamp="2025-08-11T13:00:00+00:00", close=999),
                    replace(data[-1], timestamp="2025-08-12T20:00:00+00:00", close=888)]
    strategy = EntryPolicyStrategy(config(), "A")
    costs = BacktestCosts()
    risk = MatchedEntryRisk(strategy, costs)
    adapter = IntradayEvaluation(strategy, risk, {"TEST": contaminated}, costs)
    adapter.decide("TEST", minutes()[:1], None)
    assert strategy.records[-1].indicator_price == data[-1].close
    assert risk.timestamp == minutes()[0].timestamp


def test_same_completed_daily_data_forces_a_then_next_evaluation_general_exit() -> None:
    strategy = EntryPolicyStrategy(config(), "A")
    costs = BacktestCosts()
    risk = MatchedEntryRisk(strategy, costs)
    adapter = IntradayEvaluation(strategy, risk, {"TEST": daily_history()}, costs)
    result = Backtester(adapter, risk, costs=costs, max_trade_risk_pct=.01,
                        fill_observer=strategy, risk_includes_costs=True).run(
                            {"TEST": minutes()}, starting_cash=60)
    assert [fill.side for fill in result.trades] == ["buy", "sell"]
    assert result.trades[0].price == 10
    assert result.trades[1].signal_timestamp == result.trades[0].timestamp
    assert strategy.records[0].data_fingerprint == strategy.records[1].data_fingerprint


@pytest.mark.parametrize("policy", ["B", "C"])
def test_no_minimum_entry_for_b_and_c_on_repeated_five_minute_events(policy: str) -> None:
    strategy = EntryPolicyStrategy(config(), policy)
    costs = BacktestCosts()
    risk = MatchedEntryRisk(strategy, costs)
    adapter = IntradayEvaluation(strategy, risk, {"TEST": daily_history()}, costs)
    result = Backtester(adapter, risk, costs=costs, fill_observer=strategy).run(
        {"TEST": minutes()}, starting_cash=60)
    assert result.trades == ()
    assert all(record.buy_score == 0 for record in strategy.records)


def test_duplicate_daily_c_still_evaluates_fresh_mark_hard_stop() -> None:
    strategy = EntryPolicyStrategy(config(), "C")
    costs = BacktestCosts()
    risk = MatchedEntryRisk(strategy, costs)
    adapter = IntradayEvaluation(strategy, risk, {"TEST": daily_history()}, costs)
    adapter.decide("TEST", minutes()[:1], None)
    held = Position("TEST", 1, 9.5, 10)
    decision = adapter.decide("TEST", minutes()[:2], held)
    assert decision.action == "sell" and decision.reasons == ["fixed_stop_loss"]
    assert strategy.records[-1].duplicate_general_evaluation


def test_filter_requires_end_labels_and_discards_incomplete_or_afterhours() -> None:
    rows = [*minutes(), replace(minutes()[0], timestamp="2025-08-11T13:30:00+00:00"),
            replace(minutes()[0], timestamp="2025-08-11T20:05:00+00:00")]
    result = filter_completed_intraday({"TEST": rows}, (session(),),
                                      observed_at="2025-08-11T13:42:00+00:00",
                                      timestamp_semantics="interval_end")
    assert [bar.timestamp for bar in result["TEST"]] == [bar.timestamp for bar in minutes()[:2]]
    with pytest.raises(ExperimentInputError, match="interval_end"):
        filter_completed_intraday({"TEST": rows}, (session(),),
                                  observed_at="2025-08-11T21:00:00+00:00",
                                  timestamp_semantics="unknown")


def test_replay_freezes_protocol_and_does_not_extrapolate_partial_month(tmp_path: Path) -> None:
    import json

    run_intraday_replay(config(), {"TEST": daily_history()}, {"TEST": minutes()},
                       (session(),), tmp_path, (CostScenario("zero", 0, 0, 0, 0, "unit fixture"),),
                       fx_rate=1400, manifest={"synthetic": True, "bar_timestamp_semantics": "interval_end",
                                               "collected_at": "2025-08-11T21:00:00+00:00"})
    protocol = json.loads((tmp_path / "protocol.json").read_text())
    assert protocol["indicator_timeframe"] == "1Day"
    assert protocol["execution_timeframe"] == "5Min"
    with pytest.raises(ExperimentInputError, match="frozen protocol"):
        run_intraday_replay(config(), {"TEST": daily_history()}, {"TEST": minutes()},
                           (session(),), tmp_path, (), fx_rate=1400,
                           manifest={"bar_timestamp_semantics": "interval_end",
                                     "collected_at": "2025-08-11T21:00:00+00:00"})


def test_unknown_provider_label_uses_explicit_five_minute_availability_lag() -> None:
    result = filter_completed_intraday({"TEST": minutes()}, (session(),),
                                      observed_at="2025-08-11T13:42:00+00:00",
                                      timestamp_semantics="available_after_next_label")
    assert [bar.timestamp for bar in result["TEST"]] == ["2025-08-11T13:40:00+00:00"]


def test_irregular_label_cannot_be_reported_as_five_minute_observation() -> None:
    invalid = replace(minutes()[0], timestamp="2025-08-11T13:36:00+00:00")
    with pytest.raises(ExperimentInputError, match="five-minute grid"):
        filter_completed_intraday({"TEST": [invalid]}, (session(),),
                                  observed_at="2025-08-11T21:00:00+00:00",
                                  timestamp_semantics="interval_end")


def test_existing_nonempty_output_is_preserved_even_without_protocol(tmp_path: Path) -> None:
    sentinel = tmp_path / "summary.csv"
    sentinel.write_text("existing user result\n", encoding="utf-8")
    with pytest.raises(ExperimentInputError, match="nonempty"):
        run_intraday_replay(config(), {"TEST": daily_history()}, {"TEST": minutes()},
                           (session(),), tmp_path, (CostScenario("zero", 0, 0, 0, 0, "unit fixture"),),
                           fx_rate=1400, manifest={"bar_timestamp_semantics": "interval_end",
                                                 "collected_at": "2025-08-11T21:00:00+00:00"})
    assert sentinel.read_text(encoding="utf-8") == "existing user result\n"
