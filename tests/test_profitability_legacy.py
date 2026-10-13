from __future__ import annotations

import csv
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nasdaq_auto_trader.backtest import Backtester
from nasdaq_auto_trader.backtest_costs import BacktestCosts
from nasdaq_auto_trader.entry_comparison import EntryEvaluation, load_entry_profile
from nasdaq_auto_trader.entry_comparison_risk import MatchedEntryRisk
from nasdaq_auto_trader.entry_policy_experiment import EntryPolicyStrategy
from nasdaq_auto_trader.exit_experiment import EvaluationSplit
from nasdaq_auto_trader.exit_experiment_config import CostScenario
from nasdaq_auto_trader.models import Bar
from nasdaq_auto_trader.profitability_legacy import run_legacy_diagnostics

ROOT = Path(__file__).resolve().parents[1]
COSTS = (CostScenario("base", 0.0025, 0, 10, 10, "test"),)


def histories() -> dict[str, list[Bar]]:
    start = datetime(2025, 1, 1, 21, tzinfo=UTC)
    return {
        symbol: [
            Bar(
                symbol,
                (start + timedelta(days=i)).isoformat(),
                price + i * 0.002 + math.sin(i / 5) * 0.05,
                price + i * 0.002 + math.sin(i / 5) * 0.05 + 0.02,
                price + i * 0.002 + math.sin(i / 5) * 0.05 - 0.02,
                price + i * 0.002 + math.sin(i / 5) * 0.05,
                10000,
            )
            for i in range(90)
        ]
        for symbol, price in (("HIGH", 40), ("LOW", 2))
    }


def test_diagnostics_preserve_original_fills_rejections_and_equity(
    tmp_path: Path,
) -> None:
    # Given unchanged A/B/C inputs and an existing real simulator.
    config = load_entry_profile(ROOT / "experiments/entry_policy/profile.json")
    bars = histories()
    split = EvaluationSplit(
        "test", bars["LOW"][64].timestamp, bars["LOW"][-1].timestamp
    )
    # When diagnostic observers are attached.
    runs = run_legacy_diagnostics(
        config, bars, (split,), COSTS, fx_rate=1400, fx_history=(), output=tmp_path
    )
    # Then they leave every execution result unchanged.
    assert len(runs) == 3
    for run in runs:
        cost = BacktestCosts(0.0025, 0, 10, 10, 1)
        strategy = EntryPolicyStrategy(config, run.policy)
        risk = MatchedEntryRisk(strategy, cost)
        original = Backtester(
            EntryEvaluation(strategy, risk, split, cost),
            risk,
            costs=cost,
            max_trade_risk_pct=0.01,
            max_total_position_pct=0.5,
            fill_observer=strategy,
            risk_includes_costs=True,
        ).run(bars, starting_cash=80000 / 1400)
        assert run.result == original


def test_diagnostics_report_coincident_and_signal_hidden_limits(tmp_path: Path) -> None:
    # Given a $40 share in an 80,000 KRW account with 50% and 1% limits.
    config = load_entry_profile(ROOT / "experiments/entry_policy/profile.json")
    bars = histories()
    split = EvaluationSplit(
        "test", bars["LOW"][64].timestamp, bars["LOW"][-1].timestamp
    )
    # When all original policies are observed.
    _ = run_legacy_diagnostics(
        config, bars, (split,), COSTS, fx_rate=1400, fx_history=(), output=tmp_path
    )
    # Then early-return reasons do not hide other mathematical failures.
    with (tmp_path / "diagnostics.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    high = [row for row in rows if row["symbol"] == "HIGH"]
    assert high
    assert all(row["single_position_limit"] == "True" for row in high)
    assert all(row["max_order_notional_limit"] == "True" for row in high)
    assert all(row["risk_budget_exceeded"] == "True" for row in high)
    assert any(row["first_reason"] == "total_exposure_limit_50pct" for row in high)
    assert any(row["no_buy_signal"] == "True" for row in high)


def test_diagnostics_preserve_nonempty_output(tmp_path: Path) -> None:
    # Given an unrelated existing file.
    sentinel = tmp_path / "notes.txt"
    _ = sentinel.write_text("preserve", encoding="utf-8")
    # When diagnostics are pointed at that directory.
    with pytest.raises(ValueError, match="empty"):
        _ = run_legacy_diagnostics(
            load_entry_profile(ROOT / "experiments/entry_policy/profile.json"),
            histories(),
            (),
            COSTS,
            fx_rate=1400,
            fx_history=(),
            output=tmp_path,
        )
    # Then no existing bytes or output files change.
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert not (tmp_path / "diagnostics.csv").exists()
