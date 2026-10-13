from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from contextlib import AbstractContextManager
from typing import Protocol, assert_never

from .brokers.kis_reconciliation import KISCancelOrder, KISCancelResult, KISOpenOrder, KISOrderHistory
from .live_canary_policy import CANARY_POLICY, OrderSide
from .live_canary_state import CanaryState, KnownOrder
from .models import Position


class CanaryReconciliationBroker(Protocol):
    def reconciliation_window(
        self,
        deadline_seconds: float,
    ) -> AbstractContextManager[None]: ...

    def list_positions(self, refresh: bool = False) -> dict[str, Position]: ...

    def list_open_orders(self) -> tuple[KISOpenOrder, ...]: ...

    def list_order_history(self, start_date: str, end_date: str) -> tuple[KISOrderHistory, ...]: ...

    def cancel_order(self, order: KISCancelOrder) -> KISCancelResult: ...


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    state: CanaryState
    reason: str
    cancelled_orders: int = 0

    @property
    def manual_required(self) -> bool:
        return self.state.mode.value == "manual_reconciliation_required"


def reconcile_startup(
    state: CanaryState,
    broker: CanaryReconciliationBroker,
    market_date: str,
    now: datetime,
) -> ReconciliationResult:
    if state.intent is not None:
        return _manual(state, "durable_intent_without_order_id")
    with broker.reconciliation_window(CANARY_POLICY.reconciliation_tick_deadline_seconds):
        positions = broker.list_positions(refresh=True)
        open_orders = broker.list_open_orders()
        history = broker.list_order_history(
            market_date.replace("-", ""),
            market_date.replace("-", ""),
        )
    if state.known_order is None:
        if open_orders:
            return _manual(state, "foreign_open_order")
        return _reconcile_owned(state, positions)
    return _reconcile_known(
        state,
        broker,
        positions,
        open_orders,
        history,
        state.known_order,
        now,
    )


def owned_position_matches(state: CanaryState, positions: dict[str, Position]) -> bool:
    if state.owned_symbol is None:
        return not positions
    position = positions.get(state.owned_symbol)
    return (
        len(positions) == 1
        and position is not None
        and position.symbol == state.owned_symbol
        and position.qty == state.max_owned_quantity
        and position.avg_entry_price > 0
    )


def _reconcile_owned(state: CanaryState, positions: dict[str, Position]) -> ReconciliationResult:
    if owned_position_matches(state, positions):
        return ReconciliationResult(state, "startup_reconciled")
    return _manual(state, "foreign_or_missing_position")


def _reconcile_known(
    state: CanaryState,
    broker: CanaryReconciliationBroker,
    positions: dict[str, Position],
    open_orders: tuple[KISOpenOrder, ...],
    history: tuple[KISOrderHistory, ...],
    known: KnownOrder,
    now: datetime,
) -> ReconciliationResult:
    matching_open = tuple(order for order in open_orders if _matches_open(order, known))
    if len(matching_open) == 1 and len(open_orders) == 1:
        if not _known_open_position_matches(state, positions):
            return _manual(state, "open_order_position_mismatch")
        result = matching_open[0]
        if known.submitted_at is None:
            return ReconciliationResult(
                state.with_known_order_submitted_at(now),
                "known_open_order_pending",
            )
        if not _cancellation_due(known, now):
            return ReconciliationResult(state, "known_open_order_pending")
        cancelled = _cancel_exact(known, result, state, broker)
        return cancelled
    if open_orders:
        return _manual(state, "foreign_or_ambiguous_open_order")
    match known.side:
        case OrderSide.BUY:
            return _confirm_buy(state, positions, history, known)
        case OrderSide.SELL:
            return _confirm_sell(state, positions, history, known)
        case unreachable:
            assert_never(unreachable)


def _cancel_exact(
    known: KnownOrder,
    open_order: KISOpenOrder,
    state: CanaryState,
    broker: CanaryReconciliationBroker,
) -> ReconciliationResult:
    request = KISCancelOrder(
        known.order_id,
        known.symbol,
        known.side.value,
        open_order.remaining_quantity,
        known.limit_price_usd,
    )
    confirmation = broker.cancel_order(request)
    if confirmation.order_id != known.order_id:
        return _manual(state, "cancel_order_id_mismatch")
    return ReconciliationResult(
        state.require_manual_reconciliation(),
        "cancel_finality_requires_reconciliation",
        1,
    )


def _confirm_buy(
    state: CanaryState,
    positions: dict[str, Position],
    history: tuple[KISOrderHistory, ...],
    known: KnownOrder,
) -> ReconciliationResult:
    position = positions.get(known.symbol)
    if _history_has_exact_fill(history, known) and position is not None and len(positions) == 1:
        if position.qty == known.quantity and position.avg_entry_price > 0:
            return ReconciliationResult(
                state.confirm_owned_position(known.symbol, known.quantity, Decimal(str(position.avg_entry_price))),
                "known_buy_filled",
            )
    return _manual(state, "known_buy_not_reconciled")


def _confirm_sell(
    state: CanaryState,
    positions: dict[str, Position],
    history: tuple[KISOrderHistory, ...],
    known: KnownOrder,
) -> ReconciliationResult:
    if not positions and _history_has_exact_fill(history, known):
        return ReconciliationResult(state.confirm_exit(known.order_id), "known_sell_filled")
    return _manual(state, "known_sell_not_reconciled")


def _matches_open(order: KISOpenOrder, known: KnownOrder) -> bool:
    return (
        order.order_id == known.order_id
        and order.symbol == known.symbol
        and order.side == known.side.value
        and order.quantity == known.quantity
        and order.filled_quantity == 0
        and order.remaining_quantity > 0
        and Decimal(str(order.limit_price)) == known.limit_price_usd
    )


def _known_open_position_matches(state: CanaryState, positions: dict[str, Position]) -> bool:
    if state.owned_symbol is None:
        return not positions
    return owned_position_matches(state, positions)


def _cancellation_due(known: KnownOrder, now: datetime) -> bool:
    if known.submitted_at is None:
        return False
    submitted_at = datetime.fromisoformat(known.submitted_at)
    match known.side:
        case OrderSide.BUY:
            timeout_seconds = CANARY_POLICY.buy_order_timeout_seconds
        case OrderSide.SELL:
            timeout_seconds = CANARY_POLICY.sell_order_timeout_seconds
        case unreachable:
            assert_never(unreachable)
    return now >= submitted_at + timedelta(seconds=timeout_seconds)


def _history_has_exact_fill(history: tuple[KISOrderHistory, ...], known: KnownOrder) -> bool:
    return any(
        row.order_id == known.order_id
        and row.symbol == known.symbol
        and row.side == known.side.value
        and row.quantity == known.quantity
        and row.filled_quantity == known.quantity
        and row.average_fill_price > 0
        for row in history
    )


def _manual(state: CanaryState, reason: str) -> ReconciliationResult:
    return ReconciliationResult(state.require_manual_reconciliation(), reason)
