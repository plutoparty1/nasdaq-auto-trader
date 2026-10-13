"""Exact quantity costs and additional offline fill safeguards for P1/P2."""
from __future__ import annotations

from dataclasses import dataclass
from math import inf, isfinite
from typing import override

from .backtest_costs import BacktestCosts
from .backtest_execution import ExecutionBook, PendingOrder
from .models import AccountSnapshot, Bar, TradeDecision


@dataclass(frozen=True, slots=True)
class QuantityAssessment:
    qty: int
    planned_risk: float
    buy_fee: float
    sell_fee: float
    adverse_cost: float
    blockers: tuple[str, ...]


def planned_loss(qty: int, price: float, stop: float, costs: BacktestCosts) -> float:
    """Fees are charged per order, including quantity-dependent minimum fees."""
    return (qty * (price - stop) + costs.fee(qty * price) + costs.fee(qty * stop)
            + qty * (price + stop) * costs.adverse_fraction)


def assess_quantity(
    qty: int, price: float, stop: float | None, costs: BacktestCosts,
    account: AccountSnapshot, used_risk: float,
) -> QuantityAssessment:
    """Check the frozen caps at submission or the actual next opening price."""
    valid = (stop is not None and all(isfinite(value) for value in
             (price, stop, account.cash, account.equity, account.buying_power, used_risk))
             and 0 < stop < price and account.equity > 0
             and min(account.cash, account.buying_power, used_risk) >= 0)
    if not valid or stop is None:
        return QuantityAssessment(qty, inf, 0, 0, 0, ('invalid_sizing_input',))
    notional = qty * price
    buy_fee, sell_fee = costs.fee(notional), costs.fee(qty * stop)
    adverse = qty * (price + stop) * costs.adverse_fraction
    risk = qty * (price - stop) + buy_fee + sell_fee + adverse
    flags = (
        ('integer_quantity_step', qty <= 0 or not costs.valid_qty(qty)),
        ('trade_risk_budget', risk > account.equity * .02 + 1e-10),
        ('portfolio_risk_limit', used_risk + risk > account.equity * .06 + 1e-10),
        ('symbol_position_limit', notional > (account.equity - buy_fee) * .5 + 1e-10),
        ('total_exposure_limit', account.equity - account.cash + notional
         > (account.equity - buy_fee) * .5 + 1e-10),
        ('order_notional_limit', notional > 35 + 1e-10),
        ('buying_power_limit', notional + buy_fee > account.buying_power + 1e-10),
        ('cash_with_costs', notional + buy_fee > account.cash - account.equity * .05 + 1e-10),
    )
    return QuantityAssessment(qty, risk, buy_fee, sell_fee, adverse,
                              tuple(name for name, blocked in flags if blocked))


class DynamicExecutionBook(ExecutionBook):
    """Mutable offline book; retained risk uses exact order costs, never fee times shares."""

    @override
    def _planned_risk(self, decision: TradeDecision, qty: float, price: float) -> float:
        if self.observer is None or not isfinite(qty) or qty <= 0 or not float(qty).is_integer():
            return inf
        stop = self.observer.initial_stop_for(decision.symbol, decision.latest_price)
        fill_stop = self.observer.initial_stop_for(decision.symbol, price)
        if (stop is None or fill_stop is None
                or not all(isfinite(value) for value in (price, decision.latest_price, stop, fill_stop))
                or not 0 < stop < decision.latest_price or not 0 < fill_stop < price):
            return inf
        original = planned_loss(int(qty), decision.latest_price, stop, self.costs)
        at_fill = planned_loss(int(qty), price, fill_stop, self.costs)
        return max(original + qty * max(price - decision.latest_price, 0), at_fill)

    @override
    def _buy(self, pending: PendingOrder, bar: Bar, price: float, impact: float) -> None:
        qty = self.costs.buy_qty(pending.order, price, self.account(available=True).cash)
        if qty <= 0 or not float(qty).is_integer():
            self.reject(pending, bar.timestamp, 'insufficient_cash_or_integer_quantity_at_fill')
            return
        if pending.order.symbol in self.positions:
            self.reject(pending, bar.timestamp, 'additional_buy_forbidden_at_fill')
            return
        stop = None if self.observer is None else self.observer.initial_stop_for(bar.symbol, price)
        used = sum(self.position_risk.values()) + sum(item.risk for item in self.pending.values())
        assessment = assess_quantity(int(qty), price, stop, self.costs,
                                     self.account(available=True), used)
        if assessment.blockers:
            self.reject(pending, bar.timestamp, assessment.blockers[0] + '_at_fill')
            return
        super()._buy(pending, bar, price, impact)
