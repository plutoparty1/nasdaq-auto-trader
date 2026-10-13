from __future__ import annotations

from dataclasses import dataclass
from math import floor, isclose, isfinite

from .models import Bar, OrderRequest


@dataclass(frozen=True, slots=True)
class BacktestCosts:
    """Explicit simulation assumptions; rates are fractions, spread is full bid/ask bps."""

    commission_pct: float = 0.0
    minimum_commission: float = 0.0
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    quantity_step: float = 1e-8

    def __post_init__(self) -> None:
        for value in (
            self.commission_pct,
            self.minimum_commission,
            self.spread_bps,
            self.slippage_bps,
        ):
            if not isfinite(value) or value < 0:
                raise ValueError("backtest costs must be finite and nonnegative")
        if not isfinite(self.quantity_step) or self.quantity_step <= 0:
            raise ValueError("quantity_step must be finite and positive")
        if self.adverse_fraction >= 1:
            raise ValueError("spread/slippage must be less than the execution price")

    @property
    def adverse_fraction(self) -> float:
        return (self.spread_bps / 2 + self.slippage_bps) / 10_000

    def fee(self, notional: float) -> float:
        return max(notional * self.commission_pct, self.minimum_commission)

    def floor_qty(self, quantity: float) -> float:
        return max(
            floor(quantity / self.quantity_step + 1e-9) * self.quantity_step, 0.0
        )

    def valid_qty(self, quantity: float) -> bool:
        return (
            isfinite(quantity)
            and quantity > 0
            and isclose(
                quantity / self.quantity_step,
                round(quantity / self.quantity_step),
                abs_tol=1e-7,
                rel_tol=0,
            )
        )

    def affordable_qty(self, cash: float, price: float) -> float:
        return self.floor_qty(
            min(
                (cash - self.minimum_commission) / price,
                cash / (price * (1 + self.commission_pct)),
            )
        )

    def fill_price(self, order: OrderRequest, bar: Bar) -> tuple[float, float] | None:
        buy = order.side == "buy"
        reference = bar.open
        if order.type == "limit":
            limit = order.limit_price
            if limit is None:
                return None
            if (buy and bar.low > limit) or (not buy and bar.high < limit):
                return None
            reference = min(bar.open, limit) if buy else max(bar.open, limit)
        fill = reference * (
            1 + self.adverse_fraction if buy else 1 - self.adverse_fraction
        )
        if order.limit_price is not None and order.type == "limit":
            fill = min(fill, order.limit_price) if buy else max(fill, order.limit_price)
        return fill, abs(fill - reference)

    def invalid_order(self, order: OrderRequest) -> str | None:
        if order.type not in {"market", "limit"} or order.time_in_force not in {
            "day",
            "gtc",
        }:
            return "unsupported_order_type_or_duration"
        if order.qty is not None and (
            order.notional is not None or not self.valid_qty(order.qty)
        ):
            return "invalid_quantity_or_step"
        if order.notional is not None and (
            not isfinite(order.notional) or order.notional <= 0
        ):
            return "invalid_notional"
        if order.type == "limit" and (
            order.limit_price is None
            or not isfinite(order.limit_price)
            or order.limit_price <= 0
        ):
            return "invalid_limit_price"
        if order.side == "buy" and order.qty is None and order.notional is None:
            return "missing_order_size"
        if order.side == "sell" and order.notional is not None:
            return "notional_sell_unsupported"
        return None

    def buy_qty(self, order: OrderRequest, price: float, cash: float) -> float:
        if order.qty is not None:
            return (
                order.qty
                if order.qty * price + self.fee(order.qty * price) <= cash + 1e-10
                else 0.0
            )
        if order.notional is None:
            return 0.0
        return min(
            self.floor_qty(order.notional / price),
            self.affordable_qty(cash, price),
        )
