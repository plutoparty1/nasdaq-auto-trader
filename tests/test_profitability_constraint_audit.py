import csv
import hashlib
import json
from pathlib import Path

import pytest


def write_rows(path: Path, rows: list[dict[str, str | float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["symbol"])
        writer.writeheader()
        writer.writerows(rows)


def fixture_files(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "saved"
    source.mkdir()
    bars = tmp_path / "bars.csv"
    write_rows(bars, [{"symbol": symbol, "timestamp": f"2026-01-{day:02d}T21:00:00+00:00",
                      "open": 10, "high": 10.5, "low": 9.5, "close": 10, "volume": 1000}
                     for symbol in ("AAA", "BBB", "CCC") for day in range(1, 20)])
    protocol = {"manifest": {"bars_sha256": hashlib.sha256(bars.read_bytes()).hexdigest()},
                "costs": [{"name": "base", "commission_pct": 0, "minimum_commission": 0,
                           "spread_bps": 0, "slippage_bps": 0, "source": "fixture"}]}
    (source / "protocol.json").write_text(json.dumps(protocol), encoding="utf-8")
    for name in ("constraints", "orders", "fills", "order_rejections", "equity"):
        write_rows(source / f"{name}.csv", [])
    return source, bars


def row(day: int, symbol: str = "AAA") -> dict[str, str | float]:
    return {"split": "final", "profile": "fixed_8_risk4", "policy": "fixed_8",
            "risk_pct": 0.04, "cost_scenario": "base",
            "timestamp": f"2026-01-{day:02d}T21:00:00+00:00", "symbol": symbol}


def test_audit_counts_held_and_earlier_alphabetical_pending_without_changing_source(tmp_path: Path) -> None:
    # Given a held AAA share and a newly accepted BBB order before CCC's evaluation.
    from nasdaq_auto_trader.profitability_constraint_audit import (
        audit_saved_constraints,
    )

    source, bars = fixture_files(tmp_path)
    write_rows(source / "orders.csv", [row(1) | {"qty": 1, "price": 10, "planned_risk": 0.8},
                                      row(2, "BBB") | {"qty": 1, "price": 10, "planned_risk": 0.8}])
    write_rows(source / "fills.csv", [row(2) | {"signal_timestamp": row(1)["timestamp"],
                                              "side": "buy", "qty": 1, "price": 10}])
    write_rows(source / "order_rejections.csv", [row(3, "BBB") | {
        "signal_timestamp": row(2)["timestamp"], "reason": "limit_not_touched_expired"}])
    write_rows(source / "constraints.csv", [row(2, "CCC") | {
        "first_reason": "no_buy_signal", "blocking_conditions": "('no_buy_signal',)",
        "planned_risk": 0.8, "risk_budget": 1.2, "price": 10}])
    write_rows(source / "equity.csv", [row(2) | {"equity": 30}])
    before = {path.name: path.read_bytes() for path in source.iterdir()}
    # When enriching the saved rows without rerunning the strategy.
    output = audit_saved_constraints(source, bars, tmp_path / "audit")
    with (output / "portfolio-constraints.csv").open(newline="", encoding="utf-8") as handle:
        result = next(csv.DictReader(handle))
    # Then the hidden portfolio block is added while its upstream reason and source remain intact.
    assert float(result["portfolio_used_risk_usd"]) == pytest.approx(1.6)
    assert result["counterfactual_portfolio_block"] == "True"
    assert result["source_first_reason"] == "no_buy_signal"
    assert "portfolio_risk_limit" in result["enriched_blocking_conditions"]
    assert {path.name: path.read_bytes() for path in source.iterdir()} == before


def test_rejected_and_expired_pending_do_not_use_budget_but_end_data_reservations_do(tmp_path: Path) -> None:
    # Given an immediate rejection, a prior expired order and a final-session reservation.
    from nasdaq_auto_trader.profitability_constraint_audit import (
        audit_saved_constraints,
    )

    source, bars = fixture_files(tmp_path)
    write_rows(source / "orders.csv", [row(1) | {"qty": 1, "price": 10, "planned_risk": 0.8},
                                      row(1, "BBB") | {"qty": 1, "price": 10, "planned_risk": 0.8},
                                      row(3) | {"qty": 1, "price": 10, "planned_risk": 0.8}])
    write_rows(source / "order_rejections.csv", [
        row(1) | {"signal_timestamp": row(1)["timestamp"], "reason": "portfolio_risk_limit"},
        row(2, "BBB") | {"signal_timestamp": row(1)["timestamp"], "reason": "limit_not_touched_expired"},
        row(3) | {"signal_timestamp": row(3)["timestamp"], "reason": "end_of_data_unfilled"}])
    write_rows(source / "constraints.csv", [row(2, "CCC") | {
        "first_reason": "no_buy_signal", "blocking_conditions": "('no_buy_signal',)",
        "planned_risk": 0.8, "risk_budget": 2, "price": 10}, row(3, "CCC") | {
        "first_reason": "no_buy_signal", "blocking_conditions": "('no_buy_signal',)",
        "planned_risk": 0.8, "risk_budget": 2, "price": 10}])
    # When reconstructing pending risk at each saved decision.
    output = audit_saved_constraints(source, bars, tmp_path / "audit")
    with (output / "portfolio-constraints.csv").open(newline="", encoding="utf-8") as handle:
        results = list(csv.DictReader(handle))
    # Then expired and rejected orders clear while end-of-data cleanup remains after evaluation.
    assert [float(item["portfolio_used_risk_usd"]) for item in results] == pytest.approx([0, 0.8])


def test_audit_rejects_fill_that_would_invalidate_retained_planned_risk(tmp_path: Path) -> None:
    # Given a saved buy claims a fill above its original limit.
    from nasdaq_auto_trader.profitability_constraint_audit import (
        audit_saved_constraints,
    )

    source, bars = fixture_files(tmp_path)
    write_rows(source / "orders.csv", [row(1) | {"qty": 1, "price": 10, "planned_risk": 0.8}])
    write_rows(source / "fills.csv", [row(2) | {"signal_timestamp": row(1)["timestamp"],
                                              "side": "buy", "qty": 1, "price": 10.1}])
    # When the audit tries to assign the original planned loss to that fill.
    with pytest.raises(ValueError, match="fill|risk|limit"):
        audit_saved_constraints(source, bars, tmp_path / "audit")
    # Then no partial audit artifact is published.
    assert not (tmp_path / "audit").exists()


@pytest.mark.parametrize("day,reason", [(4, "invalid_or_missing_entry_atr"), (16, "entry_stop_outside_bounds")])
def test_atr_unavailability_is_distinct_from_valid_atr_outside_bounds(tmp_path: Path, day: int, reason: str) -> None:
    # Given the saved generic stop rejection with either insufficient or wide daily ATR.
    from nasdaq_auto_trader.profitability_constraint_audit import (
        audit_saved_constraints,
    )

    source, bars = fixture_files(tmp_path)
    write_rows(source / "constraints.csv", [row(day) | {
        "profile": "entry_atr14x3_1day_risk4", "policy": "entry_atr14x3_1day",
        "first_reason": "invalid_initial_stop_or_atr",
        "blocking_conditions": "('invalid_initial_stop_or_atr',)",
        "planned_risk": "", "risk_budget": 2, "price": 10}])
    # When only already available daily observations are checked.
    output = audit_saved_constraints(source, bars, tmp_path / "audit")
    with (output / "portfolio-constraints.csv").open(newline="", encoding="utf-8") as handle:
        result = next(csv.DictReader(handle))
    # Then data absence and a valid but excessive ATR stop are separately identified.
    assert result["entry_atr_diagnostic"] == reason
    assert result["counterfactual_portfolio_block"] == ""
