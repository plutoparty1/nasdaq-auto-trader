from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from nasdaq_auto_trader.backtest_costs import BacktestCosts
from nasdaq_auto_trader.experimental_exit_models import ExitPolicy
from nasdaq_auto_trader.models import AccountSnapshot, Bar, Position, TradeDecision
from nasdaq_auto_trader.strategy_config import StrategyConfig


def bars(price: float) -> list[Bar]:
    start = datetime(2026, 1, 1, 21, tzinfo=UTC)
    return [Bar("TEST", (start + timedelta(days=index)).isoformat(), price,
                price + 0.01, price - 0.01, price, 1000) for index in range(70)]


@pytest.mark.parametrize("risk_pct", [0.01, 0.02, 0.04])
def test_higher_risk_budget_never_bypasses_fixed_one_share(risk_pct: float) -> None:
    # Given a cheap one-share order fits every budget but variable sizing could buy more.
    from nasdaq_auto_trader.profitability_risk import ProfitabilityRisk
    from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy

    costs = BacktestCosts(commission_pct=0.0025, quantity_step=1)
    strategy = ProfitabilityStrategy(StrategyConfig(long_sma=20), ExitPolicy())
    strategy.decide("TEST", bars(2), None)
    risk = ProfitabilityRisk(strategy, costs, risk_pct)
    risk.timestamp = bars(2)[-1].timestamp
    decision = TradeDecision("TEST", "buy", 9, 2, ["qualifying_fixture"], 0.1696)
    # When the common owner limits size an otherwise permitted buy.
    order = risk.build_order(decision, AccountSnapshot(50, 50, 50), None, 2)
    # Then all risk budgets still submit precisely one share.
    assert order is not None and order.qty == 1
    assert risk.records[-1].planned_qty == 1
    assert risk.records[-1].risk_only_qty >= 2


def test_all_simultaneous_blocks_are_retained_beside_first_reason() -> None:
    # Given a flat no-signal evaluation whose one share exceeds several independent caps.
    from nasdaq_auto_trader.profitability_risk import ProfitabilityRisk
    from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy

    strategy = ProfitabilityStrategy(StrategyConfig(long_sma=20), ExitPolicy())
    decision = strategy.decide("TEST", bars(40), None)
    risk = ProfitabilityRisk(strategy, BacktestCosts(quantity_step=1), 0.01)
    risk.timestamp = bars(40)[-1].timestamp
    # When account cash and buying power cannot fund the minimum whole share.
    order = risk.build_order(decision, AccountSnapshot(5, 50, 4), None, 40)
    # Then the first block and all calculable co-blockers remain distinct.
    row = risk.records[-1]
    assert order is None and row.first_reason == "no_buy_signal"
    assert {"no_buy_signal", "trade_risk_budget", "symbol_position_limit",
            "total_exposure_limit", "order_notional_limit", "cash_with_costs",
            "buying_power_limit"}.issubset(row.blocking_conditions)
    assert row.portfolio_check == "engine_submission_and_fill"


def test_wider_stop_cannot_keep_one_share_when_cost_inclusive_budget_fails() -> None:
    # Given a 10% stop consumes more than the 1% account budget for one share.
    from nasdaq_auto_trader.profitability_risk import ProfitabilityRisk
    from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy

    strategy = ProfitabilityStrategy(StrategyConfig(long_sma=20), ExitPolicy(fixed_stop_pct=0.10))
    strategy.decide("TEST", bars(10), None)
    costs = BacktestCosts(commission_pct=0.0025, quantity_step=1)
    risk = ProfitabilityRisk(strategy, costs, 0.01)
    decision = TradeDecision("TEST", "buy", 9, 10, [], 1.0475)
    # When sizing from the initial stop and roundtrip costs.
    order = risk.build_order(decision, AccountSnapshot(50, 50, 50), None, 10)
    # Then no fractional share or cost-free risk exception is introduced.
    assert order is None
    assert "trade_risk_budget" in risk.records[-1].blocking_conditions
    assert risk.records[-1].risk_only_qty == 0


def test_daily_halt_still_allows_protective_sell() -> None:
    # Given the account has lost more than the common 2% daily threshold.
    from nasdaq_auto_trader.profitability_risk import ProfitabilityRisk
    from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy

    strategy = ProfitabilityStrategy(StrategyConfig(long_sma=20), ExitPolicy())
    strategy.decide("TEST", bars(2), None)
    risk = ProfitabilityRisk(strategy, BacktestCosts(quantity_step=1), 0.04)
    risk.timestamp = "2026-04-01T20:00:00+00:00"
    buy = TradeDecision("TEST", "buy", 9, 2, [], 0.16)
    risk.build_order(buy, AccountSnapshot(50, 50, 50), None, 2)
    # When equity falls and a sell is requested.
    blocked = risk.build_order(buy, AccountSnapshot(48, 48, 48), None, 2)
    sell = risk.build_order(replace(buy, action="sell"), AccountSnapshot(48, 48, 48),
                            Position("TEST", 1, 2, 2), 2)
    # Then the buy halts but risk reduction remains possible.
    assert blocked is None and "daily_loss_buy_halt" in risk.records[-1].blocking_conditions
    assert sell is not None and sell.side == "sell"


def test_strategy_duplicate_is_first_even_when_other_conditions_also_block() -> None:
    # Given a repeated completed bar also lacks a buy signal and exceeds the risk budget.
    from nasdaq_auto_trader.profitability_risk import ProfitabilityRisk
    from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy

    strategy = ProfitabilityStrategy(StrategyConfig(long_sma=20), ExitPolicy())
    data = bars(40)
    strategy.decide("TEST", data, None)
    decision = strategy.decide("TEST", data, None)
    risk = ProfitabilityRisk(strategy, BacktestCosts(quantity_step=1), 0.01)
    # When the downstream constraint ledger observes that suppressed decision.
    risk.build_order(decision, AccountSnapshot(50, 50, 50), None, 40)
    # Then the actual upstream blocker stays first alongside hypothetical sizing blockers.
    row = risk.records[-1]
    assert row.first_reason == "completed_bar_already_evaluated"
    assert {"no_buy_signal", "trade_risk_budget"}.issubset(row.blocking_conditions)


def test_cost_inclusive_one_share_risk_is_not_charged_twice_at_fill() -> None:
    # Given one share fits the budget only when its already included fees stay single.
    from nasdaq_auto_trader.backtest_execution import ExecutionBook
    from nasdaq_auto_trader.profitability_execution import ConservativeCosts
    from nasdaq_auto_trader.profitability_risk import ProfitabilityRisk
    from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy

    costs = ConservativeCosts(minimum_commission=0.1, quantity_step=1)
    strategy = ProfitabilityStrategy(StrategyConfig(long_sma=20), ExitPolicy())
    data = bars(2)
    strategy.decide("TEST", data, None)
    risk = ProfitabilityRisk(strategy, costs, 0.01)
    risk.timestamp = data[-1].timestamp
    decision = TradeDecision("TEST", "buy", 9, 2, [], 0.36)
    account = AccountSnapshot(36.1, 36.1, 36.1)
    order = risk.build_order(decision, account, None, 2)
    assert order is not None
    book = ExecutionBook(36.1, costs, 0.06, 0.01, strategy, True,
                         max_total_position_pct=0.5)
    # When the actual execution book reserves and fills that candidate at the next open.
    book.submit(order, decision, data[-1].timestamp)
    book.execute(Bar("TEST", "2026-04-01T20:00:00+00:00", 1.99, 2.1, 1.9, 2, 1000))
    # Then entry fees affect cash exactly once and the cost-inclusive plan is retained.
    assert len(book.trades) == 1 and not book.rejections
    assert book.position_risk["TEST"] == pytest.approx(0.36)
    assert book.cash == pytest.approx(36.1 - 1.99 - 0.1)


def test_portfolio_cap_counts_both_pending_and_held_planned_losses() -> None:
    # Given each order fits a 4% trade budget but three exceed the shared 6% budget.
    from nasdaq_auto_trader.backtest_execution import ExecutionBook
    from nasdaq_auto_trader.models import OrderRequest
    from nasdaq_auto_trader.profitability_execution import ConservativeCosts

    costs = ConservativeCosts(minimum_commission=0.1, quantity_step=1)
    book = ExecutionBook(50, costs, 0.06, 0.04, risk_includes_costs=True,
                         max_total_position_pct=0.5)
    signal_time = "2026-03-31T20:00:00+00:00"
    for symbol in ("ONE", "TWO", "THREE"):
        book.submit(OrderRequest(symbol, "buy", type="limit", qty=1, limit_price=8.2),
                    TradeDecision(symbol, "buy", 9, 8.2, [], 1.02), signal_time)
    # When the first pending order fills and a third order is tried again.
    book.execute(Bar("ONE", "2026-04-01T20:00:00+00:00", 8.1, 8.3, 8, 8.2, 1000))
    book.submit(OrderRequest("THREE", "buy", type="limit", qty=1, limit_price=8.2),
                TradeDecision("THREE", "buy", 9, 8.2, [], 1.02), signal_time)
    # Then both pending-only and mixed held/pending states reject the extra planned loss.
    assert [row.reason for row in book.rejections] == ["portfolio_risk_limit"] * 2
    assert len(book.positions) == len(book.pending) == 1
