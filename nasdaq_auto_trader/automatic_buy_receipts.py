from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from math import isfinite
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .automatic_order_types import AutomaticOrderBlock
from .market_hours import EASTERN
from .models import OrderRequest, Position

if TYPE_CHECKING:
    from .engine import TradingEngine


class OrderHistoryView(Protocol):
    @property
    def order_id(self) -> str: ...

    @property
    def symbol(self) -> str: ...

    @property
    def side(self) -> str: ...

    @property
    def quantity(self) -> float: ...

    @property
    def filled_quantity(self) -> float: ...

    @property
    def average_fill_price(self) -> float: ...


@runtime_checkable
class OrderHistorySource(Protocol):
    def list_order_history(self, start_date: str, end_date: str) -> Sequence[OrderHistoryView]: ...


@runtime_checkable
class TerminalOrderHistory(Protocol):
    @property
    def status(self) -> str: ...


@runtime_checkable
class TimedOrderHistory(Protocol):
    @property
    def submitted_at(self) -> datetime | None: ...


@runtime_checkable
class OriginalOrderHistory(Protocol):
    @property
    def is_original_order(self) -> bool: ...


@runtime_checkable
class RequestedQuantityHistory(Protocol):
    @property
    def requested_quantity_known(self) -> bool: ...


def _order_time(item: OrderHistoryView) -> datetime | None:
    if not isinstance(item, TimedOrderHistory):
        return None
    timestamp = item.submitted_at
    if timestamp is None or timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return None
    return timestamp


def _valid_fill(item: OrderHistoryView) -> bool:
    return (
        bool(item.order_id)
        and item.side in {"buy", "sell"}
        and all(isfinite(value) and value >= 0 for value in (
            item.quantity, item.filled_quantity, item.average_fill_price,
        ))
        and item.filled_quantity <= item.quantity
        and (item.filled_quantity == 0 or item.average_fill_price > 0)
    )


def _position_reflected(
    buy: OrderHistoryView,
    initial_qty: float,
    position: Position | None,
    history: Sequence[OrderHistoryView],
    now: datetime,
) -> bool:
    visible_qty = position.qty if position is not None else 0.0
    if not isfinite(visible_qty) or visible_qty < 0:
        return False
    visible = Decimal(str(visible_qty))
    expected_qty = Decimal(str(initial_qty)) + Decimal(str(buy.filled_quantity))
    if visible >= expected_qty:
        return True
    buy_time = _order_time(buy)
    if buy_time is None or buy_time > now:
        return False
    seen: set[tuple[str, str]] = set()
    for item in history:
        if item.symbol != buy.symbol or item is buy:
            continue
        if isinstance(item, OriginalOrderHistory) and not item.is_original_order:
            continue
        if not _valid_fill(item):
            return False
        if item.filled_quantity == 0:
            continue
        timestamp = _order_time(item)
        if timestamp is None or timestamp > now:
            return False
        if timestamp <= buy_time:
            continue
        identity = (item.order_id, timestamp.astimezone(EASTERN).date().isoformat())
        if identity in seen:
            return False
        seen.add(identity)
        expected_qty += Decimal(str(item.filled_quantity)) * (1 if item.side == "buy" else -1)
    return 0 <= expected_qty <= visible


def automatic_buy_receipt_block(
    engine: TradingEngine,
    order: OrderRequest,
    positions: Mapping[str, Position],
) -> AutomaticOrderBlock | None:
    store = engine.automatic_order_guard.session_store
    now = engine._clock()
    for digest, receipt in store.load_buy_receipts():
        if order.side != "buy" and order.symbol != receipt.symbol:
            continue
        blocked = AutomaticOrderBlock("automatic_buy_receipt_reconciliation_pending")
        if not receipt.order_id or not isinstance(engine.broker, OrderHistorySource):
            return blocked
        history = engine.broker.list_order_history(
            receipt.market_date.replace("-", ""),
            max(receipt.market_date, now.astimezone(EASTERN).date().isoformat()).replace("-", ""),
        )
        matching = [
            item for item in history
            if (item.order_id, item.symbol, item.side)
            == (receipt.order_id, receipt.symbol, "buy")
            and (not isinstance(item, OriginalOrderHistory) or item.is_original_order)
            and (
                (timestamp := _order_time(item)) is None
                or timestamp.astimezone(EASTERN).date().isoformat() == receipt.market_date
            )
        ]
        if len(matching) != 1:
            return blocked
        item = matching[0]
        if not _valid_fill(item):
            return blocked
        status = item.status if isinstance(item, TerminalOrderHistory) else ""
        terminal = status in {
            "canceled", "cancelled", "rejected", "expired",
        }
        quantity_known = (
            not isinstance(item, RequestedQuantityHistory) or item.requested_quantity_known
        )
        fully_filled = (
            item.quantity > 0 and item.filled_quantity == item.quantity
            and (quantity_known or status == "filled")
        )
        if not (terminal or fully_filled):
            return blocked
        if item.filled_quantity > 0 and not _position_reflected(
            item, receipt.initial_position_qty, positions.get(receipt.symbol), history, now,
        ):
            if order.side == "buy":
                return blocked
            continue
        store.resolve_buy_receipt(digest)
    return None
