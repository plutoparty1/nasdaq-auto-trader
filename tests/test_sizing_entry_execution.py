import pytest

from nasdaq_auto_trader.experimental_exit_models import ExitPolicy
from nasdaq_auto_trader.models import Bar, OrderRequest, Position, TradeDecision
from nasdaq_auto_trader.profitability_execution import ConservativeCosts
from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy
from nasdaq_auto_trader.sizing_entry_execution import DynamicExecutionBook, planned_loss
from nasdaq_auto_trader.strategy_config import StrategyConfig


def make_book(costs: ConservativeCosts, cash: float = 50) -> DynamicExecutionBook:
    strategy = ProfitabilityStrategy(StrategyConfig(long_sma=20), ExitPolicy())
    return DynamicExecutionBook(cash, costs, .06, .02, strategy, True,
                                max_total_position_pct=.5)


def signal(price: float = 2) -> TradeDecision:
    return TradeDecision('TEST', 'buy', 9, price, [], .36)


def next_bar(price: float = 2) -> Bar:
    return Bar('TEST', '2026-04-02T20:00:00+00:00', price, price + .1, price - .1, price, 1000)


def test_minimum_commission_is_reserved_once_and_charged_once() -> None:
    # Given five shares fit exactly inside the $1 planned risk cap.
    costs = ConservativeCosts(minimum_commission=.1, quantity_step=1)
    book = make_book(costs)
    order = OrderRequest('TEST', 'buy', type='limit', qty=5, limit_price=2)
    # When the integer order passes the real reservation and fill path.
    book.submit(order, signal(), '2026-04-01T20:00:00+00:00')
    book.execute(next_bar())
    # Then fees are neither repeated per share nor charged twice to cash.
    assert not book.rejections and len(book.trades) == 1
    assert book.cash == pytest.approx(39.9)
    assert book.position_risk['TEST'] == pytest.approx(1)
    assert book.trades[0].qty == 5


def test_one_quantity_stays_consistent_with_original_cost_inclusive_plan() -> None:
    # Given the same one-share, zero-minimum cost assumptions as P0.
    costs = ConservativeCosts(.0025, 0, 10, 10, 1)
    book = make_book(costs)
    original_plan = .16 + costs.fee(2) + costs.fee(1.84) + 3.84 * .0015
    # When a better next open fills below the signal limit.
    book.submit(OrderRequest('TEST', 'buy', type='limit', qty=1, limit_price=2),
                signal(), '2026-04-01T20:00:00+00:00')
    book.execute(next_bar(1.99))
    # Then retained planned risk preserves the original conservative reservation.
    assert not book.rejections
    assert book.position_risk['TEST'] == pytest.approx(original_plan)


def test_order_notional_cap_rechecked_at_fill() -> None:
    # Given a deliberately injected order fits risk and cash but exceeds $35.
    book = make_book(ConservativeCosts(quantity_step=1), 1000)
    book.submit(OrderRequest('TEST', 'buy', type='limit', qty=20, limit_price=2),
                signal(), '2026-04-01T20:00:00+00:00')
    # When it reaches the actual execution path.
    book.execute(next_bar())
    # Then the fill precheck refuses it even if an upstream caller omitted a limit.
    assert not book.trades
    assert book.rejections[-1].reason == 'order_notional_limit_at_fill'


def test_deteriorating_equity_rechecks_retained_trade_risk() -> None:
    # Given a five-share reservation initially fits the account.
    book = make_book(ConservativeCosts(minimum_commission=.1, quantity_step=1))
    book.submit(OrderRequest('TEST', 'buy', type='limit', qty=5, limit_price=2),
                signal(), '2026-04-01T20:00:00+00:00')
    book.cash = 49
    # When a lower equity account reaches the next open.
    book.execute(next_bar())
    # Then the $1 planned loss no longer fits 2% of $49.
    assert not book.trades and book.rejections[-1].reason == 'trade_risk_budget_at_fill'


def test_duplicate_pending_and_additional_fill_stay_blocked() -> None:
    # Given one pending order and an already existing holding.
    book = make_book(ConservativeCosts(quantity_step=1))
    order = OrderRequest('TEST', 'buy', type='limit', qty=1, limit_price=2)
    book.submit(order, signal(), '2026-04-01T20:00:00+00:00')
    book.submit(order, signal(), '2026-04-01T20:00:00+00:00')
    book.positions['TEST'] = Position('TEST', 1, 2, 2)
    # When the pending buy reaches its opening fill.
    book.execute(next_bar())
    # Then neither a second pending buy nor averaging is allowed.
    assert not book.trades
    assert [row.reason for row in book.rejections] == [
        'duplicate_pending_order', 'additional_buy_forbidden_at_fill']


def test_fill_cannot_precede_signal_completion() -> None:
    # Given a pending order with the same timestamp as the supplied completed bar.
    book = make_book(ConservativeCosts(quantity_step=1))
    bar = next_bar()
    book.submit(OrderRequest('TEST', 'buy', type='limit', qty=1, limit_price=2),
                signal(), bar.timestamp)
    # When that same bar is offered for execution.
    book.execute(bar)
    # Then the order remains pending and has no fill.
    assert not book.trades and 'TEST' in book.pending


def test_planned_loss_equals_stop_plus_one_fee_pair_and_two_impacts() -> None:
    # Given nonzero proportional fees, a minimum fee and adverse execution.
    costs = ConservativeCosts(.0025, .1, 30, 30, 1)
    # When estimating six shares at $2 and an eight-percent stop.
    loss = planned_loss(6, 2, 1.84, costs)
    # Then the independently calculated amount contains each cost exactly once.
    assert loss == pytest.approx(.96 + .1 + .1 + 6 * 3.84 * .0045)
