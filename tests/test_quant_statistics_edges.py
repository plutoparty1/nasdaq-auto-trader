from dataclasses import fields
from datetime import datetime, timedelta, timezone
from math import isfinite, sqrt

import pytest

from nasdaq_auto_trader import quant_analytics as analytics
from nasdaq_auto_trader.ai_quant_lab.backtest_metrics import MetricTiming, calculate_backtest_metrics
from nasdaq_auto_trader.ai_quant_lab.backtest_engine import TradeLog
from nasdaq_auto_trader.quant_data.feature_statistics import aligned_beta, daily_sampling_compatible
from nasdaq_auto_trader.quant_data.features import calculate_feature_rows
from tests.ai_quant_fixtures import bars
from tests.test_quant_analytics_correctness import _price_bars


def test_returns_preserve_zero_price_loss_without_bridging_invalid_periods() -> None:
    # Given a sequence containing a complete loss and an undefined recovery base.
    prices = (100.0, 0.0, 50.0)
    # When adjacent simple returns are computed.
    returns = analytics.simple_returns(prices)
    # Then the loss is -100% and an unavailable division remains zero.
    assert returns == (-1.0, 0.0)


def test_sample_and_annualized_volatility_use_fractional_units() -> None:
    # Given symmetric fractional returns with a known sample deviation.
    returns = (-0.1, 0.1)
    # When volatility is scaled to an explicit four-period year.
    volatility = analytics.annualized_volatility(returns, 4.0)
    # Then ddof=1 and sqrt(periods) apply, without multiplying by 100.
    assert volatility == pytest.approx(sqrt(0.02) * 2)


@pytest.mark.parametrize("values", [(), (0.1,), (0.0, 0.0), (float("nan"), 0.1), (float("inf"), 0.1)])
def test_sample_standard_deviation_has_finite_unavailable_contract(values: tuple[float, ...]) -> None:
    # Given empty, insufficient, constant, or nonfinite observations.
    # When sample deviation is evaluated.
    result = analytics.sample_std(values)
    # Then unavailable estimates and a flat series remain finite zero.
    assert result == 0.0


@pytest.mark.parametrize("returns", [(), (0.0, 0.0), (0.1, 0.1), (float("nan"), 0.1), (float("inf"), 0.1)])
def test_zero_or_invalid_risk_cannot_produce_infinite_ratios(returns: tuple[float, ...]) -> None:
    # Given observations with zero or unavailable risk estimates.
    # When annualized ratios are requested.
    ratios = analytics.sharpe_ratio(returns, 252.0), analytics.sortino_ratio(returns, 252.0)
    # Then no profitable-looking infinite result can escape.
    assert ratios == (0.0, 0.0)


def test_sortino_retains_negative_constant_return_risk() -> None:
    # Given a constant loss series with zero dispersion but nonzero downside.
    returns = (-0.1, -0.1)
    # When annualized Sortino is evaluated for four periods per year.
    ratio = analytics.sortino_ratio(returns, 4.0)
    # Then the downside denominator is 0.1, yielding -2.
    assert ratio == pytest.approx(-2.0)


@pytest.mark.parametrize("curve", [(), (100.0,), (100.0, 0.0), (100.0, -1.0), (100.0, float("nan")), (100.0, float("inf"))])
def test_invalid_equity_preserves_finite_metrics(curve: tuple[float, ...]) -> None:
    # Given an absent, insufficient, or invalid equity path.
    # When the public metrics boundary is evaluated.
    result = calculate_backtest_metrics(curve, ()).to_mapping()
    # Then the persisted metrics contract is all finite, unavailable zeros.
    assert all(isfinite(value) and value == 0.0 for value in result.values())


@pytest.mark.parametrize("periods", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_sampling_basis_disables_annualization(periods: float) -> None:
    # Given valid prices but an invalid periods-per-year contract.
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timing = MetricTiming((start, start + timedelta(days=1)), periods)
    # When metrics are evaluated.
    result = calculate_backtest_metrics((100.0, 110.0), (), timing)
    # Then total return remains usable while annualization is explicitly unavailable.
    assert result.total_return == pytest.approx(0.1)
    assert not result.annualization_available
    assert result.cagr == result.sharpe == result.sortino == 0.0


def test_timing_requires_one_strictly_ordered_aware_timestamp_per_mark() -> None:
    # Given duplicate timestamps for two distinct marks.
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timing = MetricTiming((start, start), 252.0)
    # When the timing is parsed against a two-mark curve.
    result = calculate_backtest_metrics((100.0, 110.0), (), timing)
    # Then zero elapsed time cannot be annualized.
    assert not result.annualization_available


def test_drawdown_preserves_trough_after_full_recovery() -> None:
    # Given a recovered drawdown from 120 to 90.
    curve = (100.0, 120.0, 90.0, 130.0)
    # When peak-to-trough risk is evaluated.
    drawdown = analytics.max_drawdown(curve)
    # Then recovery cannot erase the earlier 25% loss.
    assert drawdown == pytest.approx(0.25)


def test_beta_normalizes_equivalent_timezone_timestamps() -> None:
    # Given identical instants represented in UTC and New York offsets.
    benchmark = _price_bars("QQQ", ("2026-01-01T21:00:00Z", "2026-01-02T21:00:00Z", "2026-01-03T21:00:00Z"), (100.0, 110.0, 132.0))
    stock = _price_bars("AAPL", ("2026-01-01T16:00:00-05:00", "2026-01-02T16:00:00-05:00", "2026-01-03T16:00:00-05:00"), (100.0, 120.0, 168.0))
    # When return intervals align by normalized instant.
    result = aligned_beta(stock, benchmark)
    # Then the beta remains two regardless of timestamp formatting.
    assert result == pytest.approx(2.0)


def test_beta_missing_benchmark_is_unavailable() -> None:
    # Given a stock history without corresponding benchmark observations.
    stock = _price_bars("AAPL", ("2026-01-01", "2026-01-02", "2026-01-03"), (100.0, 120.0, 168.0))
    # When feature rows are calculated.
    row = calculate_feature_rows({"AAPL": stock})["AAPL"]
    # Then no synthetic benchmark relationship is reported.
    assert row.beta_to_qqq == 0.0


def test_intraday_features_do_not_claim_daily_annualized_volatility() -> None:
    # Given changing intraday prices five minutes apart.
    stock = _price_bars("AAPL", ("2026-01-01T10:00:00Z", "2026-01-01T10:05:00Z", "2026-01-01T10:10:00Z"), (100.0, 120.0, 108.0))
    # When features retain per-observation volatility.
    row = calculate_feature_rows({"AAPL": stock})["AAPL"]
    # Then the daily annualization field is unavailable zero.
    assert row.volatility_20d > 0.0
    assert row.realized_volatility == 0.0


def test_daily_sampling_accepts_weekend_and_dst_gap() -> None:
    # Given a Friday-to-Monday DST weekend followed by a normal session.
    timestamps = tuple(datetime.fromisoformat(value) for value in ("2026-03-06T21:00:00+00:00", "2026-03-09T20:00:00+00:00", "2026-03-10T20:00:00+00:00"))
    # When daily compatibility is checked.
    compatible = daily_sampling_compatible(timestamps)
    # Then the conservative cadence check still supports normal session gaps.
    assert compatible


def test_features_expose_calculated_factors_without_fundamental_placeholders() -> None:
    given_history = bars("QQQ")

    when_row = calculate_feature_rows({"QQQ": given_history})["QQQ"]

    field_names = {item.name for item in fields(when_row)}
    assert field_names.isdisjoint({"quality_factor", "growth_factor", "value_factor"})
    assert when_row.momentum_factor == pytest.approx(179 / 159 - 1)
    assert when_row.liquidity_factor == pytest.approx(179 * 1_000_069.5)


@pytest.mark.parametrize("exit_cost", [100.0, 120.0])
def test_profit_factor_is_unavailable_without_realized_losses(exit_cost: float) -> None:
    given_trades = (TradeLog("QQQ", "buy", "1", 100.0, 1, 100.0), TradeLog("QQQ", "sell", "2", exit_cost, 1, exit_cost))

    when_metrics = calculate_backtest_metrics((1000.0, 1020.0), given_trades)

    assert when_metrics.profit_factor == 0.0
    assert not when_metrics.profit_factor_available
    assert when_metrics.to_mapping()["profit_factor_available"] == 0.0


def test_profit_factor_is_unavailable_without_closed_trades() -> None:
    when_metrics = calculate_backtest_metrics((1000.0, 1000.0), ())

    assert when_metrics.profit_factor == 0.0
    assert not when_metrics.profit_factor_available


def test_profit_factor_uses_actual_dollar_loss_denominator() -> None:
    given_trades = (
        TradeLog("QQQ", "buy", "1", 100.0, 1, 100.0),
        TradeLog("QQQ", "sell", "2", 120.0, 1, 120.0),
        TradeLog("QQQ", "buy", "3", 100.0, 1, 100.0),
        TradeLog("QQQ", "sell", "4", 99.0, 1, 99.0),
    )

    when_metrics = calculate_backtest_metrics((1000.0, 1020.0, 1019.0), given_trades)

    assert when_metrics.profit_factor == 20.0
    assert when_metrics.profit_factor_available
    assert when_metrics.to_mapping()["profit_factor_available"] == 1.0
