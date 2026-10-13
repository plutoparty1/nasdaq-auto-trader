from dataclasses import replace

import pytest

from nasdaq_auto_trader.backtest_costs import BacktestCosts
from nasdaq_auto_trader.backtest_execution import ExecutionBook, PendingOrder
from nasdaq_auto_trader.experimental_exit_models import ExitPolicy
from nasdaq_auto_trader.models import (
    AccountSnapshot,
    OrderRequest,
    Position,
    TradeDecision,
)
from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy
from nasdaq_auto_trader.sizing_entry_risk import DynamicEntryRisk
from nasdaq_auto_trader.strategy_config import StrategyConfig


def setup_risk(costs: BacktestCosts, cash: float = 50) -> tuple[DynamicEntryRisk, ExecutionBook]:
    strategy = ProfitabilityStrategy(StrategyConfig(long_sma=20), ExitPolicy())
    risk = DynamicEntryRisk(strategy, costs)
    book = ExecutionBook(cash, costs, .06, .02, strategy, True)
    risk.bind_book(book)
    risk.timestamp = '2026-04-01T20:00:00+00:00'
    return risk, book


def decision(price: float, costs: BacktestCosts) -> TradeDecision:
    stop = price * .92
    planned = price - stop + costs.fee(price) + costs.fee(stop)
    planned += (price + stop) * costs.adverse_fraction
    return TradeDecision('TEST', 'buy', 9, price, [], planned)


def test_maximum_quantity_accounts_for_minimum_fee_per_order() -> None:
    # Given a twenty-five-dollar account with twenty cents roundtrip minimum fee.
    costs = BacktestCosts(minimum_commission=.1, quantity_step=1)
    risk, book = setup_risk(costs, 25)
    # When each two-dollar share has a sixteen-cent stop distance.
    order = risk.build_order(decision(2, costs), book.account(available=True), None, 2)
    # Then one fee pair, not one pair per share, permits one share under fifty cents.
    assert order is not None and order.qty == 1
    assert risk.sizing_records[-1].next_qty_blockers == ('trade_risk_budget',)


def test_quantity_costs_are_not_one_share_fee_multiplied() -> None:
    # Given a fifty-dollar account whose trade risk budget is one dollar.
    costs = BacktestCosts(minimum_commission=.1, quantity_step=1)
    risk, book = setup_risk(costs)
    # When the one-dollar trade risk budget covers five sixteen-cent stops plus fees.
    order = risk.build_order(decision(2, costs), book.account(available=True), None, 2)
    # Then five shares fit exactly, although multiplying the one-share cost allows only two.
    assert order is not None and order.qty == 5
    assert risk.sizing_records[-1].planned_risk == pytest.approx(1)


def test_zero_quantity_is_never_promoted_to_one() -> None:
    # Given one share cannot fit the account's risk budget.
    costs = BacktestCosts(quantity_step=1)
    risk, book = setup_risk(costs)
    # When one share costs twenty dollars with an eight percent stop.
    order = risk.build_order(decision(20, costs), book.account(available=True), None, 20)
    # Then the risk module blocks the buy without a minimum-share exception.
    assert order is None
    assert risk.sizing_records[-1].selected_qty == 0
    assert 'trade_risk_budget' in risk.records[-1].blocking_conditions


def test_pending_and_held_risk_share_one_portfolio_budget() -> None:
    # Given held and reserved losses consume $2.8 of a $3 portfolio cap.
    costs = BacktestCosts(quantity_step=1)
    risk, book = setup_risk(costs)
    book.position_risk['HELD'] = 1.4
    prior = decision(2, costs)
    book.pending['PENDING'] = PendingOrder(OrderRequest('PENDING', 'buy', qty=1), prior, 'prior', risk=1.4)
    # When a new low-price entry could otherwise buy six shares.
    order = risk.build_order(prior, book.account(available=True), None, 2)
    # Then the remaining portfolio risk permits only one share.
    assert order is not None and order.qty == 1
    assert 'portfolio_risk_limit' in risk.sizing_records[-1].next_qty_blockers


@pytest.mark.parametrize('account', [AccountSnapshot(float('nan'), 50, 50), AccountSnapshot(50, 50, .5)])
def test_bad_account_or_unaffordable_share_blocks_buy(account: AccountSnapshot) -> None:
    # Given invalid cash or less buying power than one share costs.
    costs = BacktestCosts(quantity_step=1)
    risk, _ = setup_risk(costs)
    # When the module sizes a valid strategy signal.
    order = risk.build_order(decision(2, costs), account, None, 2)
    # Then it fails closed.
    assert order is None


def test_additional_buy_blocked_and_protective_sell_closes_all() -> None:
    # Given the dynamic position contains five shares.
    costs = BacktestCosts(quantity_step=1)
    risk, book = setup_risk(costs)
    held = Position('TEST', 5, 10, 2)
    buy = decision(2, costs)
    # When an additional buy and then a protective sell are requested.
    add = risk.build_order(buy, book.account(), held, 2)
    sell = risk.build_order(replace(buy, action='sell'), book.account(), held, 2)
    # Then averaging is refused and the entire holding can exit.
    assert add is None
    assert sell is not None and sell.qty == 5


@pytest.mark.parametrize(('account', 'price', 'expected'), [
    (AccountSnapshot(50, 50, 50), 2, 6),
    (AccountSnapshot(200, 200, 200), 2, 17),
    (AccountSnapshot(35, 50, 35), 2, 5),
    (AccountSnapshot(50, 50, 4.1), 2, 2),
])
def test_maximum_integer_satisfies_all_caps(account: AccountSnapshot, price: float, expected: int) -> None:
    # Given independently chosen trade-risk, order-notional, exposure, or cash ceilings.
    costs = BacktestCosts(quantity_step=1)
    risk, _ = setup_risk(costs)
    # When the integer sizer selects a quantity.
    order = risk.build_order(decision(price, costs), account, None, price)
    # Then every bound is satisfied and the next integer is ruled out.
    assert order is not None and order.qty == expected
    assert expected * price * .08 <= account.equity * .02 + 1e-10
    assert expected * price <= min(35, account.buying_power, account.cash - .05 * account.equity)
    assert account.equity - account.cash + expected * price <= account.equity * .5
    assert risk.sizing_records[-1].next_qty_blockers


def test_overflowing_quantity_calculation_fails_closed() -> None:
    # Given a positive finite but unrepresentably tiny price at the numeric boundary.
    costs = BacktestCosts(quantity_step=1)
    risk, book = setup_risk(costs)
    # When the quantity ratio would overflow to infinity.
    order = risk.build_order(decision(1e-310, costs), book.account(), None, 1e-310)
    # Then no exception or forced order escapes the sizing boundary.
    assert order is None
