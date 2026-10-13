from __future__ import annotations

from pathlib import Path

import pytest

from nasdaq_auto_trader.models import AccountSnapshot, TradeDecision


def test_one_share_skipped_when_cost_inclusive_loss_exceeds_budget() -> None:
    from nasdaq_auto_trader import exit_experiment_risk as module

    risk = module.ExperimentRiskManager(
        risk_pct=0.02,
        sizing="one_share",
        max_position_pct=0.8,
        cash_buffer_pct=0.1,
        monthly_loss_stop_pct=0.1,
    )
    risk.timestamp = "2025-01-02T21:00:00+00:00"
    order = risk.build_order(
        TradeDecision("TEST", "buy", 9, 10, [], 1.2),
        AccountSnapshot(50, 50, 50),
        None,
        10,
    )
    assert order is None
    assert risk.skips[-1].reason == "one_share_exceeds_risk_budget"


def test_integer_sizing_respects_risk_and_cash_reserve() -> None:
    from nasdaq_auto_trader import exit_experiment_risk as module

    risk = module.ExperimentRiskManager(
        risk_pct=0.04,
        sizing="risk_sized",
        max_position_pct=0.5,
        cash_buffer_pct=0.1,
        monthly_loss_stop_pct=0.1,
    )
    risk.timestamp = "2025-01-02T21:00:00+00:00"
    order = risk.build_order(
        TradeDecision("TEST", "buy", 9, 10, [], 0.8),
        AccountSnapshot(80, 100, 80),
        None,
        10,
    )
    assert order is not None
    assert order.qty == 5
    assert order.type == "limit"


def test_monthly_loss_halts_buys_but_allows_protection_sell() -> None:
    from nasdaq_auto_trader import exit_experiment_risk as module
    from nasdaq_auto_trader.models import Position

    risk = module.ExperimentRiskManager(
        risk_pct=0.04,
        sizing="risk_sized",
        max_position_pct=0.5,
        cash_buffer_pct=0.1,
        monthly_loss_stop_pct=0.1,
    )
    risk.timestamp = "2025-01-02T21:00:00+00:00"
    risk.build_order(
        TradeDecision("TEST", "hold", 0, 10), AccountSnapshot(100, 100, 100), None, 10
    )
    risk.timestamp = "2025-01-03T21:00:00+00:00"
    buy = risk.build_order(
        TradeDecision("TEST", "buy", 9, 10, [], 0.5),
        AccountSnapshot(80, 89, 80),
        None,
        10,
    )
    sell = risk.build_order(
        TradeDecision("TEST", "sell", 99, 9, ["fixed_stop_loss"]),
        AccountSnapshot(80, 89, 80),
        Position("TEST", 1, 9, 10),
        9,
    )
    assert buy is None
    assert sell is not None and sell.qty == 1


def test_profile_parser_rejects_live_or_unknown_settings(tmp_path: Path) -> None:
    from nasdaq_auto_trader import exit_experiment_config as module

    profile = tmp_path / "profile.json"
    profile.write_text('{"dry_run": false, "broker": "kis"}', encoding="utf-8")
    with pytest.raises(ValueError, match="offline|dry_run|fields"):
        module.load_settings(profile)


def test_cash_buffer_includes_entry_commission() -> None:
    from nasdaq_auto_trader.backtest_costs import BacktestCosts
    from nasdaq_auto_trader.exit_experiment_risk import ExperimentRiskManager

    risk = ExperimentRiskManager(
        risk_pct=0.04,
        sizing="risk_sized",
        max_position_pct=0.95,
        cash_buffer_pct=0.10,
        monthly_loss_stop_pct=0.10,
        costs=BacktestCosts(minimum_commission=1),
    )
    risk.timestamp = "2025-01-02T21:00:00+00:00"
    order = risk.build_order(
        TradeDecision("TEST", "buy", 9, 10, [], 0.1),
        AccountSnapshot(100, 100, 100),
        None,
        10,
    )
    assert order is not None and order.qty == 8
    assert 100 - order.qty * 10 - 1 >= 10


def test_total_exposure_includes_existing_and_reserved_positions() -> None:
    from nasdaq_auto_trader.exit_experiment_risk import ExperimentRiskManager

    risk = ExperimentRiskManager(
        risk_pct=0.04,
        sizing="risk_sized",
        max_position_pct=0.5,
        cash_buffer_pct=0.1,
        monthly_loss_stop_pct=0.1,
        max_total_position_pct=0.5,
    )
    risk.timestamp = "2025-01-02T21:00:00+00:00"
    order = risk.build_order(
        TradeDecision("TEST", "buy", 9, 10, [], 0.5),
        AccountSnapshot(60, 100, 60),
        None,
        10,
    )
    assert order is not None and order.qty == 1


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("costs", "commission_pct", True),
        ("costs", "commission_pct", 5),
        ("strategy", "sma_fast", 0),
        ("strategy", "stop_loss_pct", 5),
        ("strategy", "corrected_exits", "false"),
    ],
)
def test_invalid_settings_units_and_types_are_rejected(
    tmp_path: Path, section: str, field: str, value
) -> None:
    import json

    from nasdaq_auto_trader.exit_experiment_config import load_settings

    source = (
        Path(__file__).resolve().parents[1] / "experiments/early_exit/settings.json"
    )
    raw = json.loads(source.read_text())
    target = raw[section][0] if section == "costs" else raw[section]
    target[field] = value
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        load_settings(path)


def test_monthly_halt_includes_first_day_gap_from_prior_month_close() -> None:
    from nasdaq_auto_trader.exit_experiment_risk import ExperimentRiskManager

    risk = ExperimentRiskManager(
        risk_pct=0.04,
        sizing="risk_sized",
        max_position_pct=0.5,
        cash_buffer_pct=0.1,
        monthly_loss_stop_pct=0.1,
    )
    risk.timestamp = "2025-01-31T21:00:00+00:00"
    risk.build_order(
        TradeDecision("TEST", "hold", 0, 10), AccountSnapshot(100, 100, 100), None, 10
    )
    risk.timestamp = "2025-02-01T21:00:00+00:00"
    order = risk.build_order(
        TradeDecision("TEST", "buy", 9, 10, [], 0.5),
        AccountSnapshot(80, 89, 80),
        None,
        10,
    )
    assert order is None
    assert risk.skips[-1].reason == "monthly_loss_buy_halt"
