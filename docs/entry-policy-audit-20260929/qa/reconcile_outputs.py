# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python docs/entry-policy-audit-20260929/qa/reconcile_outputs.py
from __future__ import annotations

import calendar
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Final, assert_never

QA: Final = Path(__file__).resolve().parent
AUDIT: Final = QA.parent
ROOT: Final = QA.parents[2]
PUBLIC: Final = Path(os.environ["LOCALAPPDATA"]) / "NasdaqAutoTrader/research/entry-policy-20260929/public"
GROUPS: Final = ("actual-main", "actual-no-action-pair", "actual-spy-control")


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(row: dict[str, str]) -> tuple[str, str, str]:
    return row["split"], row["policy"], row["cost_scenario"]


def near(actual: float, expected: float, context: str) -> float:
    error = abs(actual - expected)
    assert error < 1e-8, (context, actual, expected, error)
    return error


def main() -> None:
    fx = rows(PUBLIC / "usdkrw.csv")
    market = {symbol: rows(PUBLIC / f"{symbol}.csv") for symbol in ("CMCSA", "KDP", "HIVE", "SPY")}
    public_manifest = json.loads((PUBLIC / "manifest.json").read_text(encoding="utf-8"))
    dividends = {stock["symbol"]: list(stock["events"].get("dividends", {}).values()) for stock in public_manifest["stocks"]}
    report = []
    snapshots = []
    for group in GROUPS:
        directory = AUDIT / group
        protocol = json.loads((directory / "protocol.json").read_text(encoding="utf-8"))
        declared = protocol.pop("protocol_sha256")
        assert hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest() == declared
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        assert protocol["data_manifest"] == manifest
        bars_file = "actual_trade_group_after_corporate_action.csv" if group == "actual-main" else "actual_trade_group.csv"
        if group == "actual-spy-control":
            bars_file = "SPY.csv"
        assert digest(PUBLIC / bars_file) == manifest["bars_sha256"]
        assert digest(PUBLIC / "usdkrw.csv") == manifest["fx_history_sha256"]
        assert digest(ROOT / "experiments/entry_policy/profile.json") == manifest["profile_sha256"]
        assert digest(ROOT / "experiments/early_exit/settings.json") == manifest["costs_sha256"]
        assert protocol["policies"] == ["A", "B", "C"]
        for key, expected in (("common_risk_pct", .01), ("quantity", 1), ("starting_krw", 80000), ("single_and_total_exposure_pct", .5), ("cash_buffer_pct", .05), ("max_order_usd", 35), ("daily_new_buy_loss_halt_pct", .02)):
            assert protocol[key] == expected
        assert protocol["historical_minimum_risk_override_5pct_included"] is False
        strategy = protocol["strategy"]
        for key, expected in (("stop_loss_pct", .03), ("take_profit_pct", .05), ("trailing_stop_activation_pct", .02), ("trailing_stop_pct", .01), ("atr_stop_multiplier", 3), ("atr_take_profit_multiplier", 5), ("atr_period", 14)):
            assert strategy[key] == expected
        fills, curves, months = (rows(directory / f"{name}.csv") for name in ("fills", "equity", "monthly"))
        summary_rows = rows(directory / "summary.csv")
        assert len({identity(row) for row in summary_rows}) == len(summary_rows)
        assert len(summary_rows) == len(protocol["splits"]) * 6
        for summary in summary_rows:
            key = identity(summary)
            selected = [row for row in fills if identity(row) == key]
            curve = [row for row in curves if identity(row) == key]
            split = next(item for item in protocol["splits"] if item["name"] == key[0])
            rate = float([point for point in fx if point["timestamp"] <= split["start"]][-1]["usdkrw"])
            starting = 80000 / rate
            cash, realized, fees, execution = starting, 0.0, 0.0, 0.0
            positions: dict[str, tuple[float, float, str]] = {}
            closed_intervals: list[tuple[str, str, str]] = []
            max_cash_error = max_equity_error = 0.0
            fill_index = 0
            cost = next(item for item in protocol["costs"] if item["name"] == key[2])
            for point in curve:
                while fill_index < len(selected) and selected[fill_index]["timestamp"] <= point["timestamp"]:
                    fill = selected[fill_index]
                    fill_index += 1
                    price, qty, fee = (float(fill[name]) for name in ("price", "qty", "fee"))
                    notional = price * qty
                    assert qty == 1 and fill["signal_timestamp"] < fill["timestamp"]
                    near(float(fill["notional"]), notional, "notional")
                    near(fee, max(notional * cost["commission_pct"], cost["minimum_commission"]), "fee")
                    symbol = fill["symbol"]
                    side = Side(fill["side"])
                    match side:
                        case Side.BUY:
                            assert symbol not in positions and notional <= 35 + 1e-9
                            positions[symbol] = (price, fee, fill["timestamp"])
                            cash -= notional + fee
                        case Side.SELL:
                            entry, entry_fee, entered = positions.pop(symbol)
                            pnl = notional - entry - entry_fee - fee
                            near(float(fill["pnl"]), pnl, "realized fill")
                            near(float(fill["allocated_entry_fee"]), entry_fee, "entry fee allocation")
                            near(float(fill["gross_pnl"]), notional - entry, "gross pnl")
                            realized += pnl
                            cash += notional - fee
                            closed_intervals.append((symbol, entered, fill["timestamp"]))
                        case _:
                            assert_never(side)
                    fees += fee
                    execution += float(fill["execution_cost"])
                value = sum(float([bar for bar in market[symbol] if bar["timestamp"] <= point["timestamp"]][-1]["close"]) for symbol in positions)
                max_cash_error = max(max_cash_error, near(float(point["cash"]), cash, "curve cash"))
                near(float(point["positions_value"]), value, "market marked holdings")
                max_equity_error = max(max_equity_error, near(float(point["equity"]), cash + value, "curve equity"))
            assert fill_index == len(selected)
            ending = float(curve[-1]["equity"])
            unrealized = sum(float([bar for bar in market[symbol] if bar["timestamp"] <= curve[-1]["timestamp"]][-1]["close"]) - entry - fee for symbol, (entry, fee, _) in positions.items())
            near(float(summary["realized_pnl_usd"]), realized, "summary realized")
            near(float(summary["unrealized_pnl_after_entry_cost_usd"]), unrealized, "summary unrealized")
            near(ending - starting, realized + unrealized, "net equity P&L")
            near(float(summary["commissions_usd"]), fees, "summary commissions")
            near(float(summary["execution_cost_usd"]), execution, "summary execution cost")
            near(float(summary["trading_cost_usd"]), fees + execution, "total cost")
            near(float(summary["cumulative_return_pct"]), (ending / starting - 1) * 100, "USD return")
            ending_fx = float([point for point in fx if point["timestamp"] <= curve[-1]["timestamp"]][-1]["usdkrw"])
            near(float(summary["cumulative_krw_return_pct"]), (ending * ending_fx / 80000 - 1) * 100, "KRW return")
            assert int(summary["completed_roundtrips"]) == len(closed_intervals)
            assert summary["literal_five_minute_exits"] == ""
            assert (summary["evidence_status"] == "no_executions") == (not selected)
            complete = target = 0
            for month in (row for row in months if identity(row) == key):
                year, number = (int(item) for item in month["month"].split("-"))
                full = split["start"][:10] <= f"{month['month']}-01" and split["end"][:10] >= f"{month['month']}-{calendar.monthrange(year, number)[1]:02d}"
                assert month["complete_calendar_window"] == str(full)
                complete += full
                target += full and float(month["usd_return_pct"]) >= 10
            assert int(summary["complete_calendar_months"]) == complete
            assert int(summary["target_complete_calendar_months"]) == target
            entitled = []
            intervals = closed_intervals + [(symbol, entry[2], "9999-12-31") for symbol, entry in positions.items()]
            for symbol, bought, sold in intervals:
                for event in dividends[symbol]:
                    exdate = datetime.fromtimestamp(event["date"], timezone.utc).date().isoformat()
                    if bought[:10] < exdate <= sold[:10]:
                        entitled.append({"symbol": symbol, "ex_date": exdate, "gross_amount_usd": event["amount"]})
            report.append({"group": group, "split": key[0], "policy": key[1], "cost": key[2], "fills": len(selected), "roundtrips": len(closed_intervals), "starting_usd": starting, "ending_usd": ending, "realized_usd": realized, "unrealized_usd": unrealized, "fee_usd": fees, "execution_cost_usd": execution, "max_cash_error": max_cash_error, "max_equity_error": max_equity_error, "full_months": complete, "target_full_months": target, "dividend_entitlements_by_public_ex_date": entitled})
        snapshots.append({"group": group, "protocol_sha256": declared, "input_bars_sha256": manifest["bars_sha256"], "profile_sha256": manifest["profile_sha256"], "costs_sha256": manifest["costs_sha256"], "fx_history_sha256": manifest["fx_history_sha256"], "artifact_sha256": {file.name: digest(file) for file in directory.iterdir() if file.is_file()}})
    (QA / "reconciliation.json").write_text(json.dumps({"status": "PASS", "groups_checked": len(report), "results": report}, indent=2), encoding="utf-8")
    (QA / "artifact-snapshot.json").write_text(json.dumps(snapshots, indent=2), encoding="utf-8")
    print(f"PASS: independently reconciled {len(report)} policy/split/cost groups, all curve points, fills, fees, FX, full-month flags, and hashes")


if __name__ == "__main__":
    main()
