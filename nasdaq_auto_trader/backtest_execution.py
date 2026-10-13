from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import isfinite

from .backtest_costs import BacktestCosts
from .backtest_types import BacktestFillObserver, BacktestRejection, BacktestTrade
from .models import AccountSnapshot, Bar, OrderRequest, Position, TradeDecision


@dataclass(frozen=True, slots=True)
class PendingOrder:
    order: OrderRequest
    decision: TradeDecision
    timestamp: str
    cash: float = 0.0
    risk: float = 0.0


@dataclass(slots=True)
class ExecutionBook:
    cash: float
    costs: BacktestCosts
    max_portfolio_risk_pct: float | None = None
    max_trade_risk_pct: float | None = None
    observer: BacktestFillObserver | None = None
    risk_includes_costs: bool = False
    max_total_position_pct: float | None = field(default=None, kw_only=True)
    positions: dict[str, Position] = field(default_factory=dict)
    pending: dict[str, PendingOrder] = field(default_factory=dict)
    trades: list[BacktestTrade] = field(default_factory=list)
    rejections: list[BacktestRejection] = field(default_factory=list)
    entry_fees: dict[str, float] = field(default_factory=dict)
    position_risk: dict[str, float] = field(default_factory=dict)

    def account(self, *, available: bool = False) -> AccountSnapshot:
        equity = self.cash + sum(p.market_value for p in self.positions.values())
        cash = (
            self.cash - sum(p.cash for p in self.pending.values())
            if available
            else self.cash
        )
        return AccountSnapshot(max(cash, 0.0), equity, max(cash, 0.0))

    def reject(self, pending: PendingOrder, timestamp: str, reason: str) -> None:
        self.rejections.append(
            BacktestRejection(
                pending.timestamp, timestamp, pending.order.symbol, reason
            )
        )

    def risk_allowed(self, risk: float, equity: float) -> bool:
        used = sum(self.position_risk.values()) + sum(
            p.risk for p in self.pending.values()
        )
        return (
            self.max_portfolio_risk_pct is None
            or used + risk <= equity * self.max_portfolio_risk_pct + 1e-10
        ) and (
            self.max_trade_risk_pct is None
            or risk <= equity * self.max_trade_risk_pct + 1e-10
        )

    def submit(
        self, order: OrderRequest, decision: TradeDecision, timestamp: str
    ) -> None:
        pending = PendingOrder(order, decision, timestamp)
        if order.symbol in self.pending:
            self.reject(pending, timestamp, "duplicate_pending_order")
            return
        reason = self.costs.invalid_order(order)
        if reason is not None:
            self.reject(pending, timestamp, reason)
            return
        if order.side == "buy":
            price = (
                order.limit_price
                if order.type == "limit"
                else decision.latest_price * (1 + self.costs.adverse_fraction)
            )
            if price is None or not isfinite(price) or price <= 0:
                self.reject(pending, timestamp, "invalid_price")
                return
            qty = self.costs.buy_qty(order, price, self.account(available=True).cash)
            if qty <= 0:
                self.reject(pending, timestamp, "insufficient_cash_or_quantity_step")
                return
            risk_per_share = decision.risk_per_share
            requires_risk = (
                self.max_portfolio_risk_pct is not None
                or self.max_trade_risk_pct is not None
            )
            if requires_risk and (
                risk_per_share is None
                or not isfinite(risk_per_share)
                or risk_per_share <= 0
            ):
                self.reject(pending, timestamp, "missing_or_invalid_risk")
                return
            risk = self._planned_risk(decision, qty, price)
            if not self.risk_allowed(risk, self.account().equity):
                self.reject(pending, timestamp, "portfolio_risk_limit")
                return
            principal = qty * price
            pending = replace(
                pending, cash=principal + self.costs.fee(principal), risk=risk
            )
        self.pending[order.symbol] = pending

    def _planned_risk(self, decision: TradeDecision, qty: float, price: float) -> float:
        distance = max(decision.risk_per_share or 0.0, 0.0)
        risk = qty * (distance + max(price - decision.latest_price, 0.0))
        if not self.risk_includes_costs:
            stop = max(price - distance, 0.0)
            risk += self.costs.fee(qty * price) + self.costs.fee(qty * stop)
            risk += qty * stop * self.costs.adverse_fraction
        return risk

    def execute(self, bar: Bar) -> None:
        pending = self.pending.pop(bar.symbol, None)
        if pending is None:
            return
        if bar.timestamp <= pending.timestamp:
            self.pending[bar.symbol] = pending
            return
        priced = self.costs.fill_price(pending.order, bar)
        if priced is None:
            if pending.order.time_in_force == "gtc":
                self.pending[bar.symbol] = pending
            else:
                self.reject(pending, bar.timestamp, "limit_not_touched_expired")
            return
        price, impact = priced
        if pending.order.side == "buy":
            self._buy(pending, bar, price, impact)
        else:
            self._sell(pending, bar, price, impact)

    def _buy(
        self, pending: PendingOrder, bar: Bar, price: float, impact: float
    ) -> None:
        account = self.account(available=True)
        qty = self.costs.buy_qty(pending.order, price, account.cash)
        if qty <= 0:
            self.reject(pending, bar.timestamp, "insufficient_cash_at_fill")
            return
        notional = qty * price
        fee = self.costs.fee(notional)
        if (
            self.max_total_position_pct is not None
            and account.equity - account.cash + notional
            > (account.equity - fee) * self.max_total_position_pct + 1e-10
        ):
            self.reject(pending, bar.timestamp, "total_position_limit_at_fill")
            return
        # Budget adverse gaps conservatively even when the stop later anchors to the fill.
        risk = self._planned_risk(pending.decision, qty, price)
        if self.observer is not None:
            stop = self.observer.initial_stop_for(bar.symbol, price)
            if stop is None or not isfinite(stop) or not 0 < stop < price:
                self.reject(pending, bar.timestamp, "invalid_initial_stop_at_fill")
                return
            round_trip = self.costs.fee(qty * price) + self.costs.fee(qty * stop)
            risk = max(
                risk,
                qty * (price - stop + stop * self.costs.adverse_fraction) + round_trip,
            )
        if not self.risk_allowed(risk, self.account().equity):
            self.reject(pending, bar.timestamp, "portfolio_risk_limit_at_fill")
            return
        previous = self.positions.get(bar.symbol)
        total_qty = qty + (previous.qty if previous else 0.0)
        basis = notional + (
            previous.qty * previous.avg_entry_price if previous else 0.0
        )
        high = (
            max(previous.high_water_price or previous.avg_entry_price, price)
            if previous
            else price
        )
        self.positions[bar.symbol] = Position(
            bar.symbol, total_qty, total_qty * price, basis / total_qty, high
        )
        self.entry_fees[bar.symbol] = self.entry_fees.get(bar.symbol, 0.0) + fee
        self.position_risk[bar.symbol] = self.position_risk.get(bar.symbol, 0.0) + risk
        self.cash -= notional + fee
        if self.observer is not None:
            self.observer.register_entry_fill(
                bar.symbol, basis / total_qty, total_qty, bar.timestamp
            )
        self.trades.append(
            BacktestTrade(
                pending.timestamp,
                bar.timestamp,
                bar.symbol,
                "buy",
                price,
                qty,
                notional,
                tuple(pending.decision.reasons),
                fee=fee,
                execution_cost=impact * qty,
            )
        )

    def _sell(
        self, pending: PendingOrder, bar: Bar, price: float, impact: float
    ) -> None:
        position = self.positions.get(bar.symbol)
        if position is None:
            self.reject(pending, bar.timestamp, "no_position")
            return
        qty = min(
            pending.order.qty if pending.order.qty is not None else position.qty,
            position.qty,
        )
        ratio = qty / position.qty
        notional = qty * price
        fee = self.costs.fee(notional)
        entry_fee = self.entry_fees[bar.symbol] * ratio
        gross = qty * (price - position.avg_entry_price)
        remaining = position.qty - qty
        if remaining <= 1e-12:
            self.positions.pop(bar.symbol)
            self.entry_fees.pop(bar.symbol)
            self.position_risk.pop(bar.symbol)
        else:
            self.positions[bar.symbol] = replace(
                position, qty=remaining, market_value=remaining * price
            )
            self.entry_fees[bar.symbol] -= entry_fee
            self.position_risk[bar.symbol] *= 1 - ratio
        self.cash += notional - fee
        if self.observer is not None:
            self.observer.register_exit_fill(bar.symbol, max(remaining, 0.0))
        self.trades.append(
            BacktestTrade(
                pending.timestamp,
                bar.timestamp,
                bar.symbol,
                "sell",
                price,
                qty,
                notional,
                tuple(pending.decision.reasons),
                pnl=gross - fee - entry_fee,
                fee=fee,
                gross_pnl=gross,
                allocated_entry_fee=entry_fee,
                execution_cost=impact * qty,
            )
        )
