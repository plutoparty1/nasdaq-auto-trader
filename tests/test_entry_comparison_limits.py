from __future__ import annotations

import json
from pathlib import Path

import pytest

from nasdaq_auto_trader.backtest_costs import BacktestCosts
from nasdaq_auto_trader.entry_comparison import load_entry_profile
from nasdaq_auto_trader.entry_comparison_risk import MatchedEntryRisk
from nasdaq_auto_trader.entry_policy_experiment import EntryPolicyStrategy
from nasdaq_auto_trader.models import AccountSnapshot, Position, TradeDecision
from nasdaq_auto_trader.strategy_config import StrategyConfig

ROOT = Path(__file__).resolve().parents[1]


def test_profile_rejects_boolean_quantity_as_number(tmp_path: Path) -> None:
    profile = json.loads((ROOT / "experiments/entry_policy/profile.json").read_text())
    profile["risk"]["order_qty"] = True
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile))
    with pytest.raises(ValueError, match="risk|quantity|type"):
        load_entry_profile(path)


def test_daily_account_loss_halts_buys_but_preserves_protective_sell() -> None:
    risk = MatchedEntryRisk(EntryPolicyStrategy(StrategyConfig(), "C"), BacktestCosts())
    risk.timestamp = "2025-01-01T21:00:00+00:00"
    risk.build_order(
        TradeDecision("TEST", "hold", 0, 10, []),
        AccountSnapshot(100, 100, 100),
        None,
        10,
    )
    risk.timestamp = "2025-01-02T21:00:00+00:00"
    buy = risk.build_order(
        TradeDecision("TEST", "buy", 5, 10, [], 0.3),
        AccountSnapshot(97, 97, 97),
        None,
        10,
    )
    sell = risk.build_order(
        TradeDecision("HELD", "sell", 99, 9, ["fixed_stop_loss"]),
        AccountSnapshot(97, 97, 97),
        Position("HELD", 1, 9, 10),
        9,
    )
    assert buy is None
    assert risk.skips[-1].reason == "daily_account_loss_buy_halt_2pct"
    assert sell is not None and sell.side == "sell"


def test_reserved_cash_counts_toward_total_exposure_before_second_order() -> None:
    risk = MatchedEntryRisk(EntryPolicyStrategy(StrategyConfig(), "B"), BacktestCosts())
    risk.timestamp = "2025-01-02T21:00:00+00:00"
    decision = TradeDecision("SECOND", "buy", 5, 20, [], 0.3)
    result = risk.build_order(decision, AccountSnapshot(65, 100, 65), None, 20)
    assert result is None
    assert risk.skips[-1].reason == "total_exposure_limit_50pct"


def test_unavailable_training_windows_are_omitted_without_moving_frozen_boundaries() -> (
    None
):
    from datetime import datetime, timedelta, timezone

    from nasdaq_auto_trader.entry_comparison_inputs import build_splits
    from nasdaq_auto_trader.models import Bar

    start = datetime(2026, 1, 6, 21, tzinfo=timezone.utc)
    bars = {
        "TEST": [
            Bar(
                "TEST",
                (start + timedelta(days=index)).isoformat(),
                10,
                10.1,
                9.9,
                10,
                100,
            )
            for index in range(100)
        ]
    }
    splits = build_splits(
        bars, "2025-08-29T23:59:59+00:00", "2026-02-27T23:59:59+00:00"
    )
    assert [split.name for split in splits] == ["final"]
    assert splits[0].start == bars["TEST"][64].timestamp


@pytest.mark.parametrize(
    "bar_time", ["2026-01-06", "2026-01-06T21:00:00", "2026-01-07T21:00:00+00:00"]
)
def test_source_rejects_ambiguous_or_not_yet_observed_bar_time(
    tmp_path: Path, bar_time: str
) -> None:
    from nasdaq_auto_trader.entry_comparison_inputs import validate_source_timestamps

    path = tmp_path / "bars.csv"
    path.write_text(
        "symbol,timestamp,open,high,low,close,volume\nTEST,"
        + bar_time
        + ",10,11,9,10,100\n"
    )
    with pytest.raises(ValueError, match="timezone|collection"):
        validate_source_timestamps(path, "2026-01-07T12:00:00+00:00")


def test_library_rejects_nonempty_output_before_writing_protocol(
    tmp_path: Path,
) -> None:
    from nasdaq_auto_trader.entry_comparison import run_entry_suite
    from nasdaq_auto_trader.models import Bar

    sentinel = tmp_path / "notes.txt"
    sentinel.write_text("unrelated user work")
    bars = {"TEST": [Bar("TEST", "2026-01-06T21:00:00+00:00", 10, 11, 9, 10, 100)]}
    with pytest.raises(ValueError, match="empty"):
        run_entry_suite(
            StrategyConfig(), bars, (), tmp_path, (), fx_rate=1400, manifest={}
        )
    assert sentinel.read_text() == "unrelated user work"
    assert not (tmp_path / "protocol.json").exists()
