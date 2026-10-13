from __future__ import annotations

from math import isclose

from nasdaq_auto_trader.backtest_costs import BacktestCosts
from nasdaq_auto_trader.backtest_types import BacktestResult, BacktestTrade, EquityPoint
from nasdaq_auto_trader.exit_experiment import EvaluationSplit
from nasdaq_auto_trader.exit_experiment_metrics import summarize
from nasdaq_auto_trader.models import Bar
from nasdaq_auto_trader.profitability_benchmarks import build_benchmarks
from nasdaq_auto_trader.profitability_metrics import additional_summary


def test_summary_includes_open_losses_and_all_model_costs() -> None:
    # Given: an open holding lost value after a paid entry.
    trade = BacktestTrade("2025-01-01", "2025-01-02", "A", "buy", 20.1,
                          1, 20.1, (), fee=0.2, execution_cost=0.1)
    result = BacktestResult(100, 89.7, (trade,), (
        EquityPoint("2025-01-02", 99.7, 79.7, 20),
        EquityPoint("2025-01-03", 89.7, 79.7, 10),
    ))
    performance = summarize(result, fx_rate=1400, operations_monthly_krw=None)
    # When: additional account metrics are computed.
    values = additional_summary(result, performance, EvaluationSplit(
        "exploratory", "2025-01-01", "2025-01-03"))
    # Then: open losses remain in net performance and cost-neutral PnL reconciles.
    assert isclose(values.net_pnl_usd, -10.3)
    assert isclose(values.unrealized_pnl_after_entry_cost_usd, -10.3)
    assert isclose(values.gross_pnl_before_model_costs_usd, -10)
    assert values.completed_roundtrips == 0
    assert values.average_net_completed_trade_usd is None
    assert isclose(values.average_invested_pct, (20 / 99.7 + 10 / 89.7) * 50)
    assert isclose(values.maximum_invested_pct, 20 / 99.7 * 100)


def test_summary_uses_only_complete_calendar_months_for_target() -> None:
    # Given: January's 10% gain is partial; February and March are complete.
    result = BacktestResult(100, 99, equity_curve=(
        EquityPoint("2025-01-31", 110, 110, 0),
        EquityPoint("2025-02-28", 121, 121, 0),
        EquityPoint("2025-03-31", 108.9, 108.9, 0),
        EquityPoint("2025-04-04", 99, 99, 0),
    ))
    performance = summarize(result, fx_rate=1400, operations_monthly_krw=None)
    # When: the four observed month buckets are summarized.
    values = additional_summary(result, performance, EvaluationSplit(
        "exploratory", "2025-01-15", "2025-04-04"))
    # Then: only two complete months enter the target denominator.
    assert values.complete_calendar_months == 2
    assert values.target_complete_calendar_months == 1
    assert values.complete_month_median_return_pct is not None
    assert values.complete_month_worst_return_pct is not None
    assert isclose(values.complete_month_median_return_pct, 0, abs_tol=1e-10)
    assert isclose(values.complete_month_worst_return_pct, -10)
    assert values.observed_months == 4


def test_completed_trade_average_excludes_partial_open_sales() -> None:
    # Given: one completed roundtrip and one partially sold open position.
    trades = (
        BacktestTrade("2025-01-01", "2025-01-02", "A", "buy", 10, 1, 10, ()),
        BacktestTrade("2025-01-02", "2025-01-03", "A", "sell", 11, 1, 11, (), pnl=1),
        BacktestTrade("2025-01-03", "2025-01-04", "B", "buy", 10, 2, 20, ()),
        BacktestTrade("2025-01-04", "2025-01-05", "B", "sell", 9, 1, 9, (), pnl=-1),
    )
    result = BacktestResult(100, 99, trades)
    performance = summarize(result, fx_rate=1400, operations_monthly_krw=None)
    # When: realized partial sales and completed trades are aggregated.
    values = additional_summary(result, performance, EvaluationSplit(
        "exploratory", "2025-01-01", "2025-01-05"))
    # Then: the partial sale is realized but does not become a completed trade.
    assert values.realized_pnl_usd == 0
    assert values.average_net_completed_trade_usd == 1


def _bars(prices: tuple[tuple[str, float, float], ...]) -> dict[str, list[Bar]]:
    return {symbol: [Bar(symbol, timestamp, opening, max(opening, close),
                         min(opening, close), close, 1000)
                     for timestamp in ("2025-01-02", "2025-01-03")]
            for symbol, opening, close in prices}


def test_benchmark_preserves_integer_budget_and_open_mark_to_market() -> None:
    # Given: $60 cannot equal-weight buy all three names; A is affordable.
    bars = _bars((("A", 10, 8), ("B", 25, 30), ("C", 40, 50)))
    costs = BacktestCosts(commission_pct=0.01, spread_bps=20, quantity_step=1)
    # When: the frozen alphabetical no-reallocation basket is evaluated.
    cases = build_benchmarks(bars, EvaluationSplit(
        "exploratory", "2025-01-02", "2025-01-03"), costs, 60)
    # Then: one A share remains open, cash and all entry costs reconcile.
    basket = cases["integer_buy_hold"]
    assert basket.included_symbols == ("A",)
    assert basket.missing_symbols == ("B", "C")
    assert basket.result.trades[0].qty == 1
    assert basket.result.trades[0].signal_timestamp == "2025-01-02"
    assert basket.result.trades[0].timestamp == "2025-01-03"
    assert basket.result.equity_curve[0].positions_value == 0
    assert isclose(basket.result.ending_value, 60 - 10.01 - 0.1001 + 8)
    assert basket.result.ending_positions[0].market_value == 8
    assert basket.result.equity_curve[-1].cash > 49
    assert basket.estimated_liquidation_value_usd < basket.result.ending_value
    assert cases["usd_cash"].result.ending_value == 60
    assert cases["fractional_reference"].status == "NONEXECUTABLE_REFERENCE"


def test_benchmark_total_limit_does_not_spend_all_allocations() -> None:
    # Given: both $18 shares fit their individual $30 allocations.
    bars = _bars((("A", 18, 18), ("B", 18, 18)))
    # When: the aggregate 50% exposure cap is applied alphabetically.
    cases = build_benchmarks(bars, EvaluationSplit(
        "exploratory", "2025-01-02", "2025-01-03"), BacktestCosts(quantity_step=1), 60)
    # Then: B is blocked despite its independent allocation being sufficient.
    basket = cases["integer_buy_hold"]
    assert basket.included_symbols == ("A",)
    assert "total_exposure_limit_50pct" in basket.feasibility.symbols[1].blocking_reasons
    assert basket.feasibility.full_basket_required_initial_cash_usd == 72


def test_benchmark_never_treats_fractional_reference_as_executable() -> None:
    # Given: no whole share is affordable under a three-symbol cash allocation.
    bars = _bars((("A", 30, 33), ("B", 40, 44), ("C", 50, 55)))
    # When: a $60 account evaluates the fixed universe.
    cases = build_benchmarks(bars, EvaluationSplit(
        "exploratory", "2025-01-02", "2025-01-03"), BacktestCosts(quantity_step=1), 60)
    # Then: the implementable outcome is cash while the 10% reference is labelled.
    assert cases["integer_buy_hold"].status == "no_trade"
    assert not cases["integer_buy_hold"].result.trades
    assert cases["integer_buy_hold"].result.return_pct == 0
    assert isclose(cases["fractional_reference"].result.return_pct, 10)
    assert cases["fractional_reference"].status == "NONEXECUTABLE_REFERENCE"


def test_benchmark_waits_for_next_bar_when_only_one_bar_exists() -> None:
    # Given: the final evaluation close has no later observed open.
    bars = _bars((("A", 10, 12),))
    # When: the benchmark ends on the signal close.
    cases = build_benchmarks(bars, EvaluationSplit(
        "exploratory", "2025-01-02", "2025-01-02"), BacktestCosts(quantity_step=1), 60)
    # Then: no price movement before the known cash conversion becomes a return.
    assert cases["integer_buy_hold"].status == "no_trade_end_of_data"
    assert cases["integer_buy_hold"].result.return_pct == 0
    assert cases["fractional_reference"].result.return_pct == 0


def test_benchmark_checks_total_exposure_after_entry_fees() -> None:
    # Given: one $30 share would equal 50% before its $1 fee.
    bars = _bars((("A", 30, 30),))
    # When: the fill would exceed 50% of post-fee $59 equity.
    cases = build_benchmarks(bars, EvaluationSplit(
        "exploratory", "2025-01-02", "2025-01-03"),
        BacktestCosts(minimum_commission=1, quantity_step=1), 60)
    # Then: the order is blocked and the fee is not charged.
    assert not cases["integer_buy_hold"].result.trades
    assert "total_exposure_limit_50pct" in cases["integer_buy_hold"].feasibility.symbols[0].blocking_reasons
