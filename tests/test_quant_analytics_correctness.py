from datetime import datetime, timedelta, timezone
from math import sqrt

import pytest

from nasdaq_auto_trader.ai_quant_lab import backtest_metrics
from nasdaq_auto_trader.ai_quant_lab.backtest_engine import BacktestEngine, BacktestRequest
from nasdaq_auto_trader.quant_data.features import PriceBar, calculate_feature_rows
from tests.ai_quant_fixtures import bars, valid_spec


def test_sortino_uses_downside_risk_instead_of_sharpe() -> None:
    # Given unequal upside and downside returns and unknown sampling frequency.
    curve = (100.0, 110.0, 104.5, 125.4)
    # When only a curve is supplied, annualized risk metrics are unavailable.
    metrics = backtest_metrics.calculate_backtest_metrics(curve, ())
    # Then no annualized ratio is invented.
    assert metrics.sharpe == metrics.sortino == metrics.cagr == 0.0


def test_cagr_uses_elapsed_calendar_years() -> None:
    # Given a two-year investment with a 21 percent cumulative return.
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    timing = backtest_metrics.MetricTiming((start, start + timedelta(days=730.5)), 252.0)
    # When the dated curve is evaluated.
    metrics = backtest_metrics.calculate_backtest_metrics((100.0, 121.0), (), timing)
    # Then CAGR is geometric annual growth rather than total return.
    assert metrics.cagr == pytest.approx(0.10)
    assert metrics.total_return == pytest.approx(0.21)


def test_annualized_sharpe_and_sortino_have_distinct_denominators() -> None:
    # Given returns of 10%, -5%, 20% sampled daily.
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timing = backtest_metrics.MetricTiming(tuple(start + timedelta(days=i) for i in range(4)), 252.0)
    average = (0.1 - 0.05 + 0.2) / 3
    sample_std = sqrt(sum((r - average) ** 2 for r in (0.1, -0.05, 0.2)) / 2)
    # When the complete dated curve is evaluated.
    metrics = backtest_metrics.calculate_backtest_metrics((100.0, 110.0, 104.5, 125.4), (), timing)
    # Then sample deviation and all-observation downside deviation annualize independently.
    assert metrics.sharpe == pytest.approx(average / sample_std * sqrt(252))
    assert metrics.sortino == pytest.approx(average / sqrt(0.05**2 / 3) * sqrt(252))


def _price_bars(symbol: str, dates: tuple[str, ...], prices: tuple[float, ...]) -> list[PriceBar]:
    return [PriceBar(symbol, day, price, price, price, price, 1000.0) for day, price in zip(dates, prices, strict=True)]


def test_beta_joins_both_return_interval_endpoints() -> None:
    # Given a missing stock observation: only Jan 1-2 and Jan 4-5 truly overlap.
    benchmark = _price_bars("QQQ", ("2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"), (100.0, 110.0, 99.0, 198.0, 237.6))
    stock = _price_bars("AAPL", ("2026-01-01", "2026-01-02", "2026-01-04", "2026-01-05"), (100.0, 120.0, 60.0, 84.0))
    # When beta is calculated on aligned one-period intervals.
    row = calculate_feature_rows({"QQQ": benchmark, "AAPL": stock})["AAPL"]
    # Then stock returns 20%,40% match benchmark 10%,20%, hence beta 2.
    assert row.beta_to_qqq == pytest.approx(2.0)


def test_backtest_records_one_equity_mark_per_bar() -> None:
    # Given daily input and a strategy that opens and liquidates positions.
    history = bars("QQQ")
    # When the actual offline engine runs.
    result = BacktestEngine().run(BacktestRequest(valid_spec(), {"QQQ": history}))
    # Then initial idle day is retained and final liquidation does not add a period.
    assert result.success
    assert len(result.equity_curve) == len(history)
    assert result.equity_curve[0] == result.equity_curve[1]


@pytest.mark.parametrize("step", [timedelta(minutes=5), timedelta(days=7)])
def test_backtest_rejects_non_daily_sampling(step: timedelta) -> None:
    # Given intraday or weekly bars incompatible with the daily strategy contract.
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = _price_bars("QQQ", tuple((start + i * step).isoformat() for i in range(4)), (100.0, 101.0, 99.0, 102.0))
    # When the engine validates frequency before evaluating the strategy.
    result = BacktestEngine().run(BacktestRequest(valid_spec(), {"QQQ": history}))
    # Then it cannot label non-daily samples as annualized daily performance.
    assert result.rejection_reasons == ("market_data_frequency_not_daily",)


def test_calmar_compares_calendar_growth_with_maximum_drawdown() -> None:
    given_curve = (100.0, 125.0, 100.0, 121.0)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    timing = backtest_metrics.MetricTiming(tuple(start + timedelta(days=243.5 * i) for i in range(4)), 252.0)

    when_metrics = backtest_metrics.calculate_backtest_metrics(given_curve, (), timing)

    assert when_metrics.calmar == pytest.approx(0.1 / 0.2)
    assert when_metrics.to_mapping()["calmar"] == pytest.approx(0.5)


@pytest.mark.parametrize("given_curve", [(100.0, 100.0, 110.0), (100.0, 90.0, 110.0)])
def test_calmar_is_unavailable_without_timing(given_curve: tuple[float, ...]) -> None:
    when_metrics = backtest_metrics.calculate_backtest_metrics(given_curve, ())

    assert when_metrics.calmar == 0.0


def test_calmar_is_unavailable_without_drawdown() -> None:
    given_curve = (100.0, 121.0)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    timing = backtest_metrics.MetricTiming((start, start + timedelta(days=730.5)), 252.0)

    when_metrics = backtest_metrics.calculate_backtest_metrics(given_curve, (), timing)

    assert when_metrics.calmar == 0.0
