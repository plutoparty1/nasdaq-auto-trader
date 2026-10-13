from nasdaq_auto_trader.backtest_types import BacktestRejection
from nasdaq_auto_trader.profitability_risk import AcceptedOrder


def test_final_buy_unfilled_at_end_still_counts_as_submitted() -> None:
    # Given: the final close produced a buy that has no later execution bar.
    from nasdaq_auto_trader.profitability_experiment import count_submitted_buys

    timestamp = "2026-09-29T20:00:00+00:00"
    orders = [AcceptedOrder(timestamp, "TEST", 1, 2, 0.2)]
    rejections = (BacktestRejection(timestamp, timestamp, "TEST", "end_of_data_unfilled"),)
    # When: submission counts are separated from fill outcomes.
    submitted = count_submitted_buys(orders, rejections)
    # Then: an order accepted by the execution book remains submitted.
    assert submitted == 1


def test_final_sell_rejection_does_not_reduce_buy_submissions() -> None:
    # Given: a previous buy was submitted and a later sell cannot execute.
    from nasdaq_auto_trader.profitability_experiment import count_submitted_buys

    orders = [AcceptedOrder("2026-09-28T20:00:00+00:00", "TEST", 1, 2, 0.2)]
    timestamp = "2026-09-29T20:00:00+00:00"
    rejections = (BacktestRejection(timestamp, timestamp, "TEST", "end_of_data_unfilled"),)
    # When: the buy-only count processes all execution rejections.
    submitted = count_submitted_buys(orders, rejections)
    # Then: the unrelated sell rejection does not remove the previous buy.
    assert submitted == 1


def test_immediate_portfolio_rejection_excludes_buy_from_submissions() -> None:
    # Given: risk sizing builds two buys, but the execution book rejects one.
    from nasdaq_auto_trader.profitability_experiment import count_submitted_buys

    timestamp = "2026-09-29T20:00:00+00:00"
    orders = [AcceptedOrder(timestamp, "ONE", 1, 2, 0.2),
              AcceptedOrder(timestamp, "TWO", 1, 2, 0.2)]
    rejections = (BacktestRejection(timestamp, timestamp, "TWO", "portfolio_risk_limit"),)
    # When: submission acceptance is counted after execution-book checks.
    submitted = count_submitted_buys(orders, rejections)
    # Then: only the buy admitted by the execution book is counted.
    assert submitted == 1
