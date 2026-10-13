from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nasdaq_auto_trader.backtest import Backtester
from nasdaq_auto_trader.backtest_costs import BacktestCosts
from nasdaq_auto_trader.models import (
    AccountSnapshot,
    Bar,
    OrderRequest,
    Position,
    TradeDecision,
)


@dataclass(frozen=True, slots=True)
class FirstBarBuy:
    def decide(
        self, symbol: str, bars: list[Bar], position: Position | None
    ) -> TradeDecision:
        return TradeDecision(
            symbol, "buy" if len(bars) == 1 else "hold", 5, bars[-1].close, [], 0.3
        )


@dataclass(frozen=True, slots=True)
class OneShareLimits:
    def build_order(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        position: Position | None,
        latest_price: float,
    ) -> OrderRequest | None:
        if decision.action != "buy":
            return None
        return OrderRequest(
            decision.symbol,
            "buy",
            type="limit",
            time_in_force="gtc",
            qty=1,
            limit_price=latest_price,
        )


@dataclass(frozen=True, slots=True)
class ObservedFills:
    stops: list[str] = field(default_factory=list)
    entries: list[str] = field(default_factory=list)

    def initial_stop_for(self, symbol: str, fill_price: float) -> float:
        self.stops.append(symbol)
        return fill_price * 0.97

    def register_entry_fill(
        self, symbol: str, price: float, qty: float, timestamp: str
    ) -> None:
        self.entries.append(symbol)

    def register_exit_fill(self, symbol: str, remaining_qty: float) -> None:
        raise AssertionError("this fixture only submits buys")


def bars(symbol: str, prices: tuple[float, ...]) -> list[Bar]:
    return [
        Bar(symbol, f"T{index:03}", price, price, price, price, 1000)
        for index, price in enumerate(prices)
    ]


def test_pending_buy_rejected_when_held_share_doubles_before_fill() -> None:
    # Given two pending shares totaling exactly $50 against $100 equity.
    observer = ObservedFills()
    engine = Backtester(
        FirstBarBuy(),
        OneShareLimits(),
        max_total_position_pct=0.5,
        fill_observer=observer,
    )
    # When AAA fills at $20 then doubles while the $30 BBB limit waits one bar.
    result = engine.run(
        {"AAA": bars("AAA", (20, 20, 40)), "BBB": bars("BBB", (30, 31, 30))},
        100,
    )
    # Then the proposed $70 exposure exceeds $60 and BBB changes no fill state.
    assert [(trade.symbol, trade.notional) for trade in result.trades] == [("AAA", 20)]
    assert [(item.symbol, item.reason) for item in result.rejections] == [
        ("BBB", "total_position_limit_at_fill")
    ]
    assert result.equity_curve[-1].cash == 80
    assert result.ending_value == 120
    assert observer.stops == observer.entries == ["AAA"]


def test_default_backtester_preserves_uncapped_fills() -> None:
    # Given existing callers do not opt into a total exposure cap.
    engine = Backtester(FirstBarBuy(), OneShareLimits())
    # When a holding doubles before the other limit fills.
    result = engine.run(
        {"AAA": bars("AAA", (20, 20, 40)), "BBB": bars("BBB", (30, 31, 30))},
        100,
    )
    # Then both legacy fills still execute.
    assert [(trade.symbol, trade.notional) for trade in result.trades] == [
        ("AAA", 20),
        ("BBB", 30),
    ]
    assert not result.rejections


@pytest.mark.parametrize(("opening", "closing", "fills"), [(20, 40, 2), (40, 20, 1)])
def test_exposure_guard_uses_current_open_not_future_close(
    opening: float,
    closing: float,
    fills: int,
) -> None:
    # Given one holding and a second pending limit share.
    held = bars("AAA", (20, 20, closing))
    held[-1] = Bar("AAA", "T002", opening, 40, 20, closing, 1000)
    engine = Backtester(FirstBarBuy(), OneShareLimits(), max_total_position_pct=0.5)
    # When the same bar's open and close imply different exposure decisions.
    result = engine.run({"AAA": held, "BBB": bars("BBB", (30, 31, 30))}, 100)
    # Then only the already observable opening mark determines admission.
    assert len(result.trades) == fills


@pytest.mark.parametrize(("price", "fills"), [(49.5, 1), (50, 0)])
def test_exposure_guard_uses_equity_after_entry_commission(
    price: float,
    fills: int,
) -> None:
    # Given a $1 fee lowers the $100 equity denominator to $99.
    engine = Backtester(
        FirstBarBuy(),
        OneShareLimits(),
        max_total_position_pct=0.5,
        costs=BacktestCosts(minimum_commission=1, quantity_step=1),
    )
    # When a single buy lands exactly at or just above the $49.50 limit.
    result = engine.run({"AAA": bars("AAA", (price, price))}, 100)
    # Then the exact boundary fills and the commission-induced breach rejects.
    assert len(result.trades) == fills
    assert result.equity_curve[-1].cash == (100 - price - 1 if fills else 100)


def test_other_pending_buy_reservation_counts_at_fill() -> None:
    # Given $30 of untouched BBB reservations and a $25 AAA candidate.
    engine = Backtester(FirstBarBuy(), OneShareLimits(), max_total_position_pct=0.5)
    # When AAA touches while BBB remains above its GTC limit.
    result = engine.run(
        {"AAA": bars("AAA", (25, 25)), "BBB": bars("BBB", (30, 31))}, 100
    )
    # Then AAA cannot consume the reserved exposure and leaves cash untouched.
    assert not result.trades
    assert result.equity_curve[-1].cash == 100
    assert result.rejections[0].reason == "total_position_limit_at_fill"


@pytest.mark.parametrize(
    "limit", [float("nan"), float("inf"), -float("inf"), 0, -0.1, 1.1]
)
def test_total_position_cap_rejects_nonfinite_or_out_of_unit_values(
    limit: float,
) -> None:
    # Given an invalid total exposure fraction.
    # When it crosses the Backtester configuration boundary.
    with pytest.raises(ValueError, match="fractions"):
        Backtester(FirstBarBuy(), OneShareLimits(), max_total_position_pct=limit)
    # Then execution never starts with an invalid cap.
