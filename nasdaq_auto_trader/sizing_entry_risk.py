"""P1/P2 maximum whole-share sizing with the original common entry gates."""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import floor, isfinite
from typing import final, override

from .backtest_costs import BacktestCosts
from .backtest_execution import ExecutionBook
from .models import AccountSnapshot, OrderRequest, Position, TradeDecision
from .profitability_risk import AcceptedOrder, EntryConstraintRecord, ProfitabilityRisk
from .profitability_strategy import ProfitabilityStrategy
from .sizing_entry_execution import assess_quantity, planned_loss


@dataclass(frozen=True, slots=True)
class SizingRecord:
    timestamp: str
    symbol: str
    selected_qty: int
    maximum_admissible_qty: int
    next_qty_blockers: tuple[str, ...]
    equity: float
    available_cash: float
    buying_power: float
    used_portfolio_risk: float
    planned_risk: float
    initial_stop: float | None
    price: float
    buy_fee: float
    stop_sell_fee: float
    adverse_cost: float


@final
class DynamicEntryRisk(ProfitabilityRisk):
    """Mutable diagnostic ledger bound to the execution book's actual reservations."""

    def __init__(self, strategy: ProfitabilityStrategy, costs: BacktestCosts) -> None:
        super().__init__(strategy, costs, .02)
        self.config = replace(self.config, order_qty=None, max_position_qty=None)
        self.book: ExecutionBook | None = None
        self.sizing_records: list[SizingRecord] = []

    def bind_book(self, book: ExecutionBook) -> None:
        self.book = book

    @override
    def build_order(
        self, decision: TradeDecision, account: AccountSnapshot,
        position: Position | None, latest_price: float,
    ) -> OrderRequest | None:
        if position is not None and decision.action == 'buy':
            return None
        day = self.timestamp[:10]
        if day != self.day:
            self.day_start_equity = self.previous_equity or account.equity
            self.day, self.day_halted = day, False
        self.previous_equity = account.equity
        self.day_halted |= account.equity <= self.day_start_equity * .98
        if position is not None:
            return super().build_order(decision, account, position, latest_price)
        record = self._diagnose(decision, account, latest_price)
        self.records.append(record)
        if record.blocking_conditions or decision.action != 'buy' or record.planned_qty == 0:
            return None
        self.strategy.register_order_accepted(decision.symbol, self.timestamp)
        self.accepted_orders.append(AcceptedOrder(self.timestamp, decision.symbol,
            record.planned_qty, latest_price, record.planned_risk or 0))
        return OrderRequest(decision.symbol, 'buy', type='limit',
                            qty=float(record.planned_qty), limit_price=latest_price)

    @override
    def _diagnose(
        self, decision: TradeDecision, account: AccountSnapshot, price: float,
    ) -> EntryConstraintRecord:
        stop = self.strategy.initial_stop_for(decision.symbol, price)
        if (stop is not None and 0 < stop < price and isfinite(account.equity)
                and not isfinite(account.equity / (price - stop))):
            return EntryConstraintRecord(self.timestamp, decision.symbol, decision.action,
                None, None, decision.action == 'buy', 'invalid_sizing_input',
                ('invalid_sizing_input',), 0, 0, None, stop, account.equity * .02,
                price, 0, None, None, 'exact_quantity_submission_and_fill')
        original = super()._diagnose(decision, account, price)
        stop = original.initial_stop
        used = (sum(self.book.position_risk.values()) + sum(item.risk for item in self.book.pending.values())
                if self.book is not None else float('nan'))
        one = assess_quantity(1, price, stop, self.costs, account, used)
        valid = 'invalid_sizing_input' not in one.blockers and self.costs.quantity_step == 1
        high = floor(min(35, account.cash, account.buying_power, account.equity * .5) / price) if valid else 0
        low = 0
        while low < high:
            middle = (low + high + 1) // 2
            check = assess_quantity(middle, price, stop, self.costs, account, used)
            if check.blockers:
                high = middle - 1
            else:
                low = middle
        quantity = low
        sizing_flags = {'trade_risk_budget', 'symbol_position_limit', 'total_exposure_limit',
                        'order_notional_limit', 'buying_power_limit', 'cash_with_costs',
                        'integer_quantity_step'}
        conditions = [reason for reason in original.blocking_conditions if reason not in sizing_flags]
        if quantity == 0:
            conditions.extend(one.blockers or ('integer_quantity_step',))
        if self.book is None:
            conditions.append('execution_book_unavailable')
        selected = quantity if not conditions and decision.action == 'buy' else 0
        assessment = assess_quantity(max(quantity, 1), price, stop, self.costs, account, used)
        next_check = assess_quantity(quantity + 1, price, stop, self.costs, account, used)
        planned = assessment.planned_risk if quantity > 0 else 0.0
        self.sizing_records.append(SizingRecord(self.timestamp, decision.symbol, selected,
            quantity, next_check.blockers, account.equity, account.cash, account.buying_power,
            used, planned, stop, price, assessment.buy_fee if quantity else 0,
            assessment.sell_fee if quantity else 0, assessment.adverse_cost if quantity else 0))
        risk_qty = 0
        if valid and stop is not None:
            risk_high = floor(account.equity * .02 / (price - stop))
            while risk_qty < risk_high:
                middle = (risk_qty + risk_high + 1) // 2
                if planned_loss(middle, price, stop, self.costs) > account.equity * .02 + 1e-10:
                    risk_high = middle - 1
                else:
                    risk_qty = middle
        priority = {'completed_bar_already_evaluated', 'conflicting_entry_exit_signal',
                    'invalid_initial_stop_or_atr'}
        first = (original.first_reason if original.first_reason in priority
                 else conditions[0] if conditions else 'accepted')
        return replace(original, first_reason=first, blocking_conditions=tuple(conditions),
                       planned_qty=selected, risk_only_qty=risk_qty, planned_risk=planned,
                       portfolio_check='exact_quantity_submission_and_fill')
