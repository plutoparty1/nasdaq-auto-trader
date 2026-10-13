import pytest

from nasdaq_auto_trader.backtest import BacktestCosts, Backtester
from nasdaq_auto_trader.models import (
    AccountSnapshot,
    Bar,
    OrderRequest,
    Position,
    TradeDecision,
)
from tests import test_early_exit_backtest as fixtures
from tests.test_early_exit_backtest_edges import FillObserver, MarketOrders

deny_network = fixtures.deny_network
pytestmark = pytest.mark.usefixtures("deny_network")


@pytest.mark.parametrize(("price", "fills"), [(8, False), (12, True)])
def test_sell_limit_honors_touch_and_better_gap(price: float, fills: bool) -> None:
    # Given a held share and a sell limit at 10.
    class SellLimit(MarketOrders):
        def build_order(
            self,
            decision: TradeDecision,
            account: AccountSnapshot,
            position: Position | None,
            latest_price: float,
        ) -> OrderRequest | None:
            if decision.action == "sell":
                return OrderRequest(
                    decision.symbol, "sell", type="limit", qty=1, limit_price=10
                )
            return super().build_order(decision, account, position, latest_price)

    engine = Backtester(fixtures.ScriptedStrategy({0: "buy", 1: "sell"}), SellLimit())
    # When the next bar is entirely below or above the sell limit.
    result = engine.run({"TEST": fixtures.bars([10, 10, price])}, 100)
    # Then a touched sell receives the better opening price; an untouched limit expires.
    assert len(result.trades) == (2 if fills else 1)
    if fills:
        assert result.trades[-1].price == price
    else:
        assert result.ending_positions[0].qty == 1


def test_duplicate_timestamp_cannot_execute_a_new_signal_in_same_bar() -> None:
    # Given duplicate observations for the same symbol and timestamp.
    duplicate = fixtures.bars([10])[0]
    engine = Backtester(fixtures.ScriptedStrategy({0: "buy"}), MarketOrders())
    # When the malformed history is supplied.
    with pytest.raises(ValueError, match="unique"):
        engine.run({"TEST": [duplicate, duplicate]}, 100)
    # Then rejection occurs before any signal or fill is processed.


def test_gap_fill_cannot_spend_cash_reserved_for_another_symbol() -> None:
    # Given two reserved $40 orders against $100 cash.
    engine = Backtester(fixtures.ScriptedStrategy({0: "buy"}), MarketOrders())
    # When the first symbol gaps to $70, leaving too little for the other reservation.
    result = engine.run(
        {"AAA": fixtures.bars([40, 70], "AAA"), "BBB": fixtures.bars([40, 40], "BBB")},
        100,
    )
    # Then the first order is rejected rather than stealing the second order's cash.
    assert [(t.symbol, t.notional) for t in result.trades] == [("BBB", 40)]
    assert result.equity_curve[-1].cash == 60
    assert result.rejections[0].reason == "insufficient_cash_at_fill"


def test_large_fill_bar_close_cannot_inflate_risk_budget_at_open() -> None:
    # Given a $2 budget and two $1.50-risk orders on consecutive dates.
    engine = Backtester(
        fixtures.ScriptedStrategy({0: "buy", 1: "buy"}, risk=1.5),
        MarketOrders(),
        max_portfolio_risk_pct=0.02,
    )
    path = fixtures.bars([10, 80, 10])
    path[1] = Bar("TEST", "T001", 10, 80, 10, 80, 1000)
    # When the following open removes the prior close's unrealized gain.
    result = engine.run({"TEST": path}, 100)
    # Then the second order cannot use the later close (or yesterday's gain) as equity.
    assert len(result.trades) == 1
    assert result.rejections[-1].reason == "portfolio_risk_limit_at_fill"


def test_fill_stop_risk_includes_minimum_round_trip_fees() -> None:
    # Given a stale low signal risk but an observed $2 stop distance and $2 total fees.
    observer = FillObserver(stop=8)
    engine = Backtester(
        fixtures.ScriptedStrategy({0: "buy"}, risk=1),
        MarketOrders(),
        costs=BacktestCosts(minimum_commission=1),
        max_trade_risk_pct=0.035,
        fill_observer=observer,
        risk_includes_costs=True,
    )
    # When the actual stop is checked before the entry is registered.
    result = engine.run({"TEST": fixtures.bars([10, 10])}, 100)
    # Then actual planned $4 loss exceeds $3.50 and no entry state is created.
    assert not result.trades
    assert not observer.entries
    assert result.rejections[0].reason == "portfolio_risk_limit_at_fill"
