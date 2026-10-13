# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
# How to run: python scripts/run_offline_tests.py -q docs/early-exit-audit-20260929/qa-review/test_artifact_review.py
"""TEST ONLY: independent arithmetic and library boundary checks."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

import pytest

QA = Path(__file__).parent
KEYS = ("split", "candidate", "sizing", "risk_budget_pct", "cost_scenario")


def rows(name: str) -> list[dict[str, str]]:
    with (QA / "smoke-final" / f"{name}.csv").open() as handle:
        return list(csv.DictReader(handle))


def key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row[field] for field in KEYS)


def test_complete_matrix_and_frozen_protocol_digest() -> None:
    # Given the actual smoke CLI artifacts.
    summary = rows("summary")
    protocol = json.loads((QA / "smoke-final/protocol.json").read_text())
    # When each comparison key and protocol digest is independently reconstructed.
    digest = protocol.pop("protocol_sha256")
    # Then all seven candidates include every requested dimension exactly once.
    assert len(summary) == len({key(row) for row in summary}) == 168
    assert len({row["candidate"] for row in summary}) == 7
    assert {row["risk_budget_pct"] for row in summary} == {"0.02", "0.04"}
    assert {row["sizing"] for row in summary} == {"one_share", "risk_sized"}
    assert {row["cost_scenario"] for row in summary} == {"base", "stress"}
    assert digest == hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()


def test_cash_fees_equity_and_months_reconcile() -> None:
    # Given independently grouped fills, marks, and monthly CSV observations.
    grouped = {name: defaultdict(list) for name in ("fills", "equity", "monthly")}
    for name, groups in grouped.items():
        for row in rows(name):
            groups[key(row)].append(row)
    protocol = json.loads((QA / "smoke-final/protocol.json").read_text())
    cost_params = {row["name"]: row for row in protocol["settings"]["costs"]}
    start = 80000 / 1400
    # When every comparison is independently accounted from its exported fills.
    for summary in rows("summary"):
        group = key(summary)
        fills, equity, months = (grouped[name][group] for name in grouped)
        cash = start
        costs = cost_params[summary["cost_scenario"]]
        for fill in fills:
            qty, price, fee = (float(fill[field]) for field in ("qty", "price", "fee"))
            assert qty.is_integer() and qty > 0
            assert fee == pytest.approx(max(costs["minimum_commission"], qty * price * costs["commission_pct"]))
            cash += qty * price * (1 if fill["side"] == "sell" else -1) - fee
            assert fill["signal_timestamp"] < fill["timestamp"]
            if summary["sizing"] == "one_share":
                assert qty == 1
        last = equity[-1]
        # Then cash, open positions, costs and stock return reconcile independently.
        assert cash == pytest.approx(float(last["cash"]))
        assert float(last["equity"]) == pytest.approx(cash + float(last["positions_value"]))
        assert float(summary["final_open_positions_value_usd"]) == pytest.approx(float(last["positions_value"]))
        assert float(summary["cumulative_return_pct"]) == pytest.approx((float(last["equity"]) / start - 1) * 100)
        fee_sum = sum(float(fill["fee"]) for fill in fills)
        impact_sum = sum(float(fill["execution_cost"]) for fill in fills)
        assert float(summary["commissions_usd"]) == pytest.approx(fee_sum)
        assert float(summary["trading_cost_usd"]) == pytest.approx(fee_sum + impact_sum)
        previous = start
        for month in months:
            value = float(month["ending_equity_usd"])
            assert float(month["usd_return_pct"]) == pytest.approx((value / previous - 1) * 100)
            previous = value
        returns = [float(month["usd_return_pct"]) for month in months]
        assert float(summary["worst_month_pct"]) == pytest.approx(min(returns))
        assert float(summary["median_monthly_return_pct"]) == pytest.approx(median(returns))
        assert int(summary["target_months"]) == sum(value >= 10 - 1e-9 for value in returns)
        assert float(summary["loss_month_ratio"]) == pytest.approx(sum(value < 0 for value in returns) / len(returns))
        assert summary["operations_cost_krw"] == summary["after_operations_return_pct"] == ""
        assert all(float(point["cash"]) >= -1e-9 for point in equity)


def test_monthly_halt_includes_first_observed_day_loss() -> None:
    # Given the previous month's ending account equity of 100.
    from nasdaq_auto_trader.exit_experiment_risk import ExperimentRiskManager
    from nasdaq_auto_trader.models import AccountSnapshot, TradeDecision

    risk = ExperimentRiskManager(risk_pct=0.04, sizing="one_share", max_position_pct=0.5, cash_buffer_pct=0.1, monthly_loss_stop_pct=0.1)
    risk.timestamp = "2020-01-31T21:00:00+00:00"
    risk.build_order(TradeDecision("TEST", "hold", 0, 10), AccountSnapshot(50, 100, 50), None, 10)
    risk.timestamp = "2020-02-01T21:00:00+00:00"
    # When another holding loses 11% of account equity on the first February bar.
    order = risk.build_order(TradeDecision("NEW", "buy", 9, 10, [], 0.5), AccountSnapshot(50, 89, 50), None, 10)
    # Then the monthly 10% loss stop blocks a new position.
    assert order is None
    assert risk.skips[-1].reason == "monthly_loss_buy_halt"


def test_split_boundaries_and_skip_ledger() -> None:
    # Given every fill and equity mark from the real CLI comparison.
    protocol = json.loads((QA / "smoke-final/protocol.json").read_text())
    intervals = {split["name"]: split for split in protocol["splits"]}
    fills = rows("fills")
    # When signals, fills, and marks are compared with each evaluation window.
    for fill in fills:
        split = intervals[fill["split"]]
        assert split["start"] <= fill["signal_timestamp"] < fill["timestamp"] <= split["end"]
    for point in rows("equity"):
        split = intervals[point["split"]]
        assert split["start"] <= point["timestamp"] <= split["end"]
    # Then skips are explicit rather than silently replaced with fractional shares.
    skips = rows("entry_skips")
    assert skips
    assert any(row["reason"] == "one_share_exceeds_risk_budget" for row in skips)
    for row in skips:
        if row["reason"] == "one_share_exceeds_risk_budget":
            assert float(row["planned_one_share_loss"]) > float(row["budget"])


def test_monthly_halt_resets_without_blocking_protective_sells() -> None:
    # Given a halted month after an 11% account loss.
    from nasdaq_auto_trader.exit_experiment_risk import ExperimentRiskManager
    from nasdaq_auto_trader.models import AccountSnapshot, Position, TradeDecision

    risk = ExperimentRiskManager(risk_pct=0.04, sizing="one_share", max_position_pct=0.5, cash_buffer_pct=0.1, monthly_loss_stop_pct=0.1)
    risk.timestamp = "2020-01-01T21:00:00+00:00"
    risk.build_order(TradeDecision("TEST", "hold", 0, 10), AccountSnapshot(50, 100, 50), None, 10)
    risk.timestamp = "2020-01-31T21:00:00+00:00"
    blocked = risk.build_order(TradeDecision("NEW", "buy", 9, 10, [], 0.5), AccountSnapshot(50, 89, 50), None, 10)
    protected = risk.build_order(TradeDecision("HELD", "sell", 99, 9, ["fixed_stop_loss"]), AccountSnapshot(50, 89, 50), Position("HELD", 1, 9, 10), 9)
    # When a new month starts without another loss.
    risk.timestamp = "2020-02-01T21:00:00+00:00"
    reset = risk.build_order(TradeDecision("NEW", "buy", 9, 10, [], 0.5), AccountSnapshot(50, 89, 50), None, 10)
    # Then protection was allowed throughout and new buying can resume.
    assert blocked is None and protected is not None and reset is not None

