# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python docs/entry-policy-audit-20260929/qa/reconcile_intraday.py
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import assert_never

from reconcile_outputs import AUDIT, QA, Side, digest, near, rows


def main() -> None:
    directory = AUDIT / "intraday-actual-comparison"
    protocol = json.loads((directory / "protocol.json").read_text(encoding="utf-8"))
    declared = protocol.pop("protocol_sha256")
    assert hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest() == declared
    assert protocol["monthly_extrapolation"] is False
    assert protocol["common_risk_pct"] == .01 and protocol["quantity"] == 1
    assert protocol["timestamp_semantics"] == "available_after_next_label"
    fills, curve, decisions = (rows(directory / f"{name}.csv") for name in ("fills", "equity", "decisions"))
    protected = {"fixed_stop_loss", "atr_stop_loss", "fixed_take_profit", "atr_take_profit", "trailing_profit_protection"}
    output = []
    for summary in rows(directory / "summary.csv"):
        policy, cost_name = summary["policy"], summary["cost_scenario"]
        selected = [row for row in fills if (row["policy"], row["cost_scenario"]) == (policy, cost_name)]
        points = [row for row in curve if (row["policy"], row["cost_scenario"]) == (policy, cost_name)]
        decision_map = {(row["symbol"], row["evaluation_timestamp"]): row for row in decisions if (row["policy"], row["cost_scenario"]) == (policy, cost_name)}
        cost = next(row for row in protocol["costs"] if row["name"] == cost_name)
        starting = 80000 / protocol["fx_rate"]
        cash, realized, fees, execution = starting, 0.0, 0.0, 0.0
        positions: dict[str, tuple[float, float, str]] = {}
        fill_index = cycles = conflict_buys = forced = no_condition = 0
        completed = 0
        holding_minutes = []
        for point in points:
            while fill_index < len(selected) and selected[fill_index]["timestamp"] <= point["timestamp"]:
                fill = selected[fill_index]
                fill_index += 1
                price, qty, fee = (float(fill[name]) for name in ("price", "qty", "fee"))
                assert qty == 1
                near(price * qty, float(fill["notional"]), "intraday notional")
                near(fee, max(price * qty * cost["commission_pct"], cost["minimum_commission"]), "intraday fee")
                symbol = fill["symbol"]
                signal = decision_map[(symbol, fill["signal_timestamp"])]
                assert signal["completed_bar_id"][:10] < fill["signal_timestamp"][:10]
                assert fill["signal_timestamp"] < fill["timestamp"]
                side = Side(fill["side"])
                match side:
                    case Side.BUY:
                        assert symbol not in positions and price <= 35
                        positions[symbol] = (price, fee, fill["timestamp"])
                        cash -= price + fee
                        conflict_buys += int(signal["sell_score"]) >= protocol["strategy"]["sell_score"]
                        forced += signal["forced"] == "True"
                        no_condition += signal["entry_condition_met"] != "True"
                    case Side.SELL:
                        entry, entry_fee, timestamp = positions.pop(symbol)
                        pnl = price - entry - entry_fee - fee
                        near(float(fill["pnl"]), pnl, "intraday realized")
                        near(float(fill["allocated_entry_fee"]), entry_fee, "intraday entry fee")
                        realized += pnl
                        cash += price - fee
                        duration = datetime.fromisoformat(fill["timestamp"]) - datetime.fromisoformat(timestamp)
                        cycles += duration == timedelta(minutes=5) and not any(reason in fill["reasons"] for reason in protected)
                        holding_minutes.append(duration.total_seconds() / 60)
                        completed += 1
                    case _:
                        assert_never(side)
                fees += fee
                execution += float(fill["execution_cost"])
            near(float(point["cash"]), cash, "intraday curve cash")
            marked = sum(float(decision_map[(symbol, point["timestamp"])]["protective_mark"]) for symbol in positions)
            near(float(point["positions_value"]), marked, "intraday mark from decision tape")
            near(float(point["equity"]), cash + marked, "intraday curve equity")
        assert fill_index == len(selected)
        ending = float(points[-1]["equity"])
        unrealized = float(points[-1]["positions_value"]) - sum(entry + fee for entry, fee, _ in positions.values())
        near(float(summary["realized_pnl_usd"]), realized, "intraday summary realized")
        near(float(summary["unrealized_pnl_after_entry_cost_usd"]), unrealized, "intraday summary unrealized")
        near(ending - starting, realized + unrealized, "intraday equity pnl")
        near(float(summary["trading_cost_usd"]), fees + execution, "intraday total cost")
        near(float(summary["period_return_pct"]), (ending / starting - 1) * 100, "intraday USD return")
        assert int(summary["completed_roundtrips"]) == completed
        if holding_minutes:
            near(float(summary["average_holding_minutes"]), sum(holding_minutes) / len(holding_minutes), "intraday holding time")
        assert int(summary["five_minute_grid_general_exit_fills"]) == cycles
        assert int(summary["entries_with_sell_signal"]) == conflict_buys
        assert int(summary["forced_entry_fills"]) == forced
        assert int(summary["entries_without_entry_condition"]) == no_condition
        assert summary["monthly_return_pct"] == summary["worst_month_pct"] == summary["literal_five_minute_exits"] == ""
        assert summary["complete_calendar_months"] == "0"
        assert summary["monthly_evidence_status"] == "insufficient_full_months"
        output.append({"policy": policy, "cost": cost_name, "fills": len(selected), "roundtrips": completed, "conflicting_buys": conflict_buys, "forced_buys": forced, "five_minute_grid_general_exits": cycles, "realized_usd": realized, "unrealized_usd": unrealized, "fees_usd": fees, "execution_cost_usd": execution, "equity_change_usd": ending - starting})
    report = {"status": "PASS", "source_limit": "No private input files opened; checks use simulated ledgers, decision marks, and protocol only. Intraday raw data hashes not independently rehashed.", "protocol_sha256": declared, "artifact_sha256": {path.name: digest(path) for path in directory.iterdir() if path.is_file()}, "results": output}
    (QA / "intraday-reconciliation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
