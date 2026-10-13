from __future__ import annotations

import pytest

from nasdaq_auto_trader.backtest import BacktestResult, EquityPoint


def test_monthly_returns_include_open_loss_and_initial_capital() -> None:
    from nasdaq_auto_trader import exit_experiment_metrics as module

    result = BacktestResult(
        100,
        90,
        (),
        (
            EquityPoint("2025-01-31T21:00:00+00:00", 110, 10, 100),
            EquityPoint("2025-02-28T21:00:00+00:00", 90, 10, 80),
        ),
    )
    metrics = module.summarize(result, fx_rate=1400, operations_monthly_krw=None)
    assert metrics.summary.cumulative_return_pct == pytest.approx(-10)
    assert metrics.months[0].usd_return_pct == pytest.approx(10)
    assert metrics.months[1].usd_return_pct == pytest.approx(-18.181818)
    assert metrics.summary.target_months == 1
    assert metrics.summary.evidence_status == "no_executions"
    assert metrics.summary.after_operations_return_pct is None


def test_fx_and_operations_are_distinct_from_stock_returns() -> None:
    from nasdaq_auto_trader import exit_experiment_metrics as module

    result = BacktestResult(
        100, 100, (), (EquityPoint("2025-01-31T21:00:00+00:00", 100, 100, 0),)
    )
    performance = module.summarize(
        result,
        fx_rate=1000,
        operations_monthly_krw=1000,
        fx_history=(module.FxPoint("2025-01-31T21:00:00+00:00", 1100),),
    )
    assert performance.summary.cumulative_return_pct == 0
    assert performance.summary.cumulative_krw_return_pct == pytest.approx(10)
    assert performance.summary.after_operations_return_pct == pytest.approx(9)
