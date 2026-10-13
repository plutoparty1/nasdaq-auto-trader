"""Portfolio and per-trade risk controls."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .models import AccountSnapshot, OrderRequest, Position, TradeDecision


@dataclass(frozen=True, slots=True)
class RiskConfig:
    """Risk limits used before an order can be sent."""

    max_position_pct: float = 0.10
    min_cash_buffer_pct: float = 0.05
    min_order_notional: float = 50.0
    max_order_notional: float | None = None
    risk_per_trade_pct: float = 0.01
    order_qty: int | None = None
    max_position_qty: int | None = None
    allow_additional_buy: bool = True
    min_cash_to_buy: float = 0.0


class RiskManager:
    """Convert strategy decisions into orders that respect account limits."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def build_order(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        position: Position | None,
        latest_price: float,
    ) -> OrderRequest | None:
        """Return an order only when action and risk limits allow it."""

        if decision.action == "hold":
            return None
        if decision.action == "sell":
            return self._sell_order(decision, position)
        return self._buy_order(decision, account, position, latest_price)

    def _buy_order(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        position: Position | None,
        latest_price: float,
    ) -> OrderRequest | None:
        """Cap a buy by target weight, cash buffer, buying power, and ATR risk."""

        current_value = position.market_value if position else 0.0
        current_qty = position.qty if position else 0.0
        if not all(
            isfinite(value) and value >= 0
            for value in (
                account.cash,
                account.equity,
                account.buying_power,
                latest_price,
                current_value,
                current_qty,
            )
        ):
            return None
        if latest_price <= 0:
            return None
        if decision.risk_per_share is not None and (
            not isfinite(decision.risk_per_share) or decision.risk_per_share < 0
        ):
            return None

        target_value = account.equity * self.config.max_position_pct
        remaining_target = max(target_value - current_value, 0.0)
        cash_after_buffer = max(
            account.cash - account.equity * self.config.min_cash_buffer_pct,
            0.0,
        )
        notional = min(remaining_target, cash_after_buffer, account.buying_power)

        if self.config.max_order_notional is not None:
            notional = min(notional, self.config.max_order_notional)

        risk_notional = self._risk_limited_notional(decision, account, latest_price)
        if risk_notional is not None:
            notional = min(notional, risk_notional)

        if self.config.order_qty is not None:
            if self.config.order_qty <= 0:
                return None
            if current_qty > 0 and not self.config.allow_additional_buy:
                return None
            if (
                self.config.max_position_qty is not None
                and current_qty + self.config.order_qty > self.config.max_position_qty
            ):
                return None
            if account.cash < self.config.min_cash_to_buy:
                return None
            if latest_price * self.config.order_qty > notional:
                return None
            return OrderRequest(
                symbol=decision.symbol,
                side="buy",
                type="limit",
                qty=float(self.config.order_qty),
                limit_price=latest_price,
            )

        order_notional = round(notional, 2)
        if order_notional > notional:
            order_notional = round(order_notional - 0.01, 2)
        if order_notional < self.config.min_order_notional:
            return None
        return OrderRequest(symbol=decision.symbol, side="buy", notional=order_notional)

    def _risk_limited_notional(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        latest_price: float,
    ) -> float | None:
        """Return the notional implied by fixed-fraction risk sizing."""

        if (
            decision.risk_per_share is None
            or decision.risk_per_share <= 0
            or self.config.risk_per_trade_pct <= 0
            or latest_price <= 0
        ):
            return None
        risk_budget = account.equity * self.config.risk_per_trade_pct
        qty = risk_budget / decision.risk_per_share
        return max(qty * latest_price, 0.0)

    def _sell_order(
        self,
        decision: TradeDecision,
        position: Position | None,
    ) -> OrderRequest | None:
        """Sell the current position only when there is something to close."""

        if position is None or position.qty <= 0:
            return None
        qty = position.qty
        if self.config.order_qty is not None and self.config.order_qty > 0:
            qty = min(qty, float(self.config.order_qty))
        return OrderRequest(symbol=decision.symbol, side="sell", qty=qty)
