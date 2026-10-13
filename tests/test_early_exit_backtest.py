import socket
from dataclasses import dataclass, field

import pytest

from nasdaq_auto_trader.backtest import Backtester
from nasdaq_auto_trader.models import (
    AccountSnapshot,
    Bar,
    OrderRequest,
    Position,
    TradeDecision,
)
from nasdaq_auto_trader.risk import RiskConfig, RiskManager


@pytest.fixture(autouse=True)
def deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("network is forbidden in offline backtest tests")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


def bars(prices: list[float], symbol: str = "TEST") -> list[Bar]:
    return [
        Bar(symbol, f"T{i:03d}", price, price, price, price, 1000)
        for i, price in enumerate(prices)
    ]


@dataclass
class ScriptedStrategy:
    actions: dict[int, str]
    risk: float = 1.0
    seen: list[Position] = field(default_factory=list)

    def decide(
        self, symbol: str, history: list[Bar], position: Position | None
    ) -> TradeDecision:
        if position is not None:
            self.seen.append(position)
        action = self.actions.get(len(history) - 1, "hold")
        match action:
            case "buy":
                return TradeDecision(
                    symbol, "buy", 8, history[-1].close, ["entry"], self.risk
                )
            case "sell":
                return TradeDecision(
                    symbol, "sell", 8, history[-1].close, ["exit"], self.risk
                )
            case _:
                return TradeDecision(symbol, "hold", 0, history[-1].close)


def risk_manager(qty: int | None = 1) -> RiskManager:
    return RiskManager(
        RiskConfig(
            max_position_pct=1,
            min_cash_buffer_pct=0,
            min_order_notional=0.01,
            risk_per_trade_pct=0,
            order_qty=qty,
        )
    )


def test_quantity_buy_fills_one_share_on_next_bar() -> None:
    # Given a one-share buy signal and a following fillable bar.
    strategy = ScriptedStrategy({0: "buy"})
    # When the actual event-driven backtester runs.
    result = Backtester(strategy, risk_manager()).run({"TEST": bars([10, 9])}, 100)
    # Then one share fills only after its signal.
    assert [
        (t.signal_timestamp, t.timestamp, t.qty, t.price) for t in result.trades
    ] == [("T000", "T001", 1, 9)]


def test_additional_notional_buy_preserves_previous_quantity_and_cost_basis() -> None:
    # Given two fixed-value market buys and a partial sell.
    class Orders(RiskManager):
        def build_order(
            self,
            decision: TradeDecision,
            account: AccountSnapshot,
            position: Position | None,
            latest_price: float,
        ) -> OrderRequest | None:
            if decision.action == "buy":
                return OrderRequest(decision.symbol, "buy", notional=20)
            if decision.action == "sell":
                return OrderRequest(decision.symbol, "sell", qty=1)
            return None

    strategy = ScriptedStrategy({0: "buy", 1: "buy", 2: "sell"})
    # When buys at 10 and 20 are followed by selling one share at 30.
    result = Backtester(strategy, Orders()).run({"TEST": bars([10, 10, 20, 30])}, 100)
    # Then the remaining two shares retain the weighted entry.
    assert strategy.seen[-1].qty == pytest.approx(2)
    assert strategy.seen[-1].avg_entry_price == pytest.approx(40 / 3)
    assert result.ending_value == pytest.approx(150)


def test_highwater_only_observes_closes_after_actual_entry() -> None:
    # Given a pre-entry spike, then entry, rise and fall.
    strategy = ScriptedStrategy({1: "buy"})
    # When held closes are 10, 12 and 11.
    Backtester(strategy, risk_manager(None)).run(
        {"TEST": bars([100, 10, 10, 12, 11])}, 100
    )
    # Then pre-entry history cannot inflate the holding high-water mark.
    assert [p.high_water_price for p in strategy.seen] == [10, 12, 12]


def test_limit_buy_requires_touch_and_honors_gap_price() -> None:
    # Given a limit at 10 with no touch on the next day.
    strategy = ScriptedStrategy({0: "buy"})
    # When all subsequent prices exceed the limit.
    result = Backtester(strategy, risk_manager()).run({"TEST": bars([10, 12, 9])}, 100)
    # Then the day order expires without filling on either day.
    assert not result.trades


def test_costs_include_both_commissions_and_adverse_execution() -> None:
    # Given a one-share round trip with 1% commission, $0.50 minimum and 20 bps spread.
    import nasdaq_auto_trader.backtest as module

    costs = module.BacktestCosts(
        commission_pct=0.01,
        minimum_commission=0.5,
        spread_bps=20,
        slippage_bps=10,
        quantity_step=1,
    )
    strategy = ScriptedStrategy({0: "buy", 1: "sell"})

    class MarketOrders(RiskManager):
        def build_order(
            self,
            decision: TradeDecision,
            account: AccountSnapshot,
            position: Position | None,
            latest_price: float,
        ) -> OrderRequest | None:
            if decision.action == "hold":
                return None
            return OrderRequest(decision.symbol, decision.action, qty=1)

    # When flat $10 bars are executed with explicitly adverse costs.
    result = Backtester(strategy, MarketOrders(), costs=costs).run(
        {"TEST": bars([10, 10, 10])}, 100
    )
    # Then realized net loss includes the allocated entry and exit commission.
    assert [t.price for t in result.trades] == pytest.approx([10.02, 9.98])
    assert [t.fee for t in result.trades] == pytest.approx([0.5, 0.5])
    assert result.trades[-1].pnl == pytest.approx(-1.04)
    assert result.ending_value == pytest.approx(98.96)


def test_quantity_steps_and_cash_prevent_fractional_or_oversized_orders() -> None:
    # Given an integer-only account with $10 cash and a $0.50 minimum fee.
    import nasdaq_auto_trader.backtest as module

    costs = module.BacktestCosts(quantity_step=1, minimum_commission=0.5)
    # When one $10 share cannot be paid for including its fee.
    result = Backtester(ScriptedStrategy({0: "buy"}), risk_manager(), costs=costs).run(
        {"TEST": bars([10, 10])}, 10
    )
    # Then no partial share or negative cash can hide the unaffordable order.
    assert not result.trades
    assert result.ending_value == 10
    assert result.rejections


def test_pending_orders_reserve_cash_before_other_symbols_size_orders() -> None:
    # Given two simultaneous independent requests for 80% of current cash.
    class CashOrders(RiskManager):
        def build_order(
            self,
            decision: TradeDecision,
            account: AccountSnapshot,
            position: Position | None,
            latest_price: float,
        ) -> OrderRequest | None:
            if decision.action == "buy":
                return OrderRequest(decision.symbol, "buy", notional=account.cash * 0.8)
            return None

    # When signals are evaluated before either one fills.
    result = Backtester(ScriptedStrategy({0: "buy"}), CashOrders()).run(
        {"AAA": bars([10, 10], "AAA"), "BBB": bars([10, 10], "BBB")}, 100
    )
    # Then the second order sees only unreserved cash (20 * 0.8).
    assert [t.notional for t in result.trades] == pytest.approx([80, 16])
    assert result.equity_curve[-1].cash == pytest.approx(4)


def test_pending_orders_and_held_positions_share_portfolio_risk_cap() -> None:
    # Given two one-share orders risking $6 each against a $10 aggregate budget.
    strategy = ScriptedStrategy({0: "buy"}, risk=6)
    # When both would individually pass the ordinary risk manager.
    result = Backtester(strategy, risk_manager(), max_portfolio_risk_pct=0.1).run(
        {"AAA": bars([10, 10], "AAA"), "BBB": bars([10, 10], "BBB")}, 100
    )
    # Then only one order can reserve that risk.
    assert len(result.trades) == 1
    assert any(r.reason == "portfolio_risk_limit" for r in result.rejections)
