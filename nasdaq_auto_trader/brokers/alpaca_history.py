from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import isfinite
from typing import TYPE_CHECKING, Final
from zoneinfo import ZoneInfo

from ..ai_quant_lab.types import JsonValue
from .common import BrokerRequestError

if TYPE_CHECKING:
    from .alpaca import AlpacaClient


_PAGE_SIZE: Final = 500
_EASTERN: Final = ZoneInfo("America/New_York")
_STATUSES: Final = frozenset({
    "", "new", "partially_filled", "filled", "done_for_day", "canceled", "expired",
    "replaced", "pending_cancel", "pending_replace", "pending_review", "accepted", "pending_new",
    "accepted_for_bidding", "stopped", "rejected", "suspended", "calculated", "held",
})


@dataclass(frozen=True, slots=True)
class AlpacaOrderHistory:
    order_id: str
    symbol: str
    side: str
    quantity: float
    filled_quantity: float
    average_fill_price: float
    status: str = ""
    submitted_at: datetime | None = None
    requested_quantity_known: bool = True


def read_order_history(
    client: AlpacaClient, start_date: str, end_date: str,
) -> tuple[AlpacaOrderHistory, ...]:
    start, end = _date_bounds(start_date, end_date)
    params: dict[str, str | int] = {
        "status": "all", "limit": _PAGE_SIZE, "nested": "false",
        "after": (start - timedelta(microseconds=1)).isoformat(),
        "until": end.isoformat(),
    }
    orders: list[AlpacaOrderHistory] = []
    seen_ids: set[str] = set()
    previous_time = end
    while True:
        payload: JsonValue = client._request("GET", client.trading_base_url, "/v2/orders", params)
        if not isinstance(payload, list) or len(payload) > _PAGE_SIZE:
            raise BrokerRequestError("Alpaca order history page invalid")
        reached_start = False
        last_id = ""
        for raw in payload:
            order_id, submitted_at, order = _parse_history(raw)
            if order_id in seen_ids:
                raise BrokerRequestError("Alpaca order history duplicate identity")
            seen_ids.add(order_id)
            last_id = order_id
            if submitted_at is None:
                if len(payload) == _PAGE_SIZE or "before_order_id" in params:
                    raise BrokerRequestError("Alpaca paginated history submission time missing")
            else:
                if submitted_at >= end or submitted_at > previous_time:
                    raise BrokerRequestError("Alpaca order history chronology invalid")
                previous_time = submitted_at
                if submitted_at < start:
                    reached_start = True
                    continue
            if order is not None:
                orders.append(order)
        if len(payload) < _PAGE_SIZE or reached_start:
            return tuple(orders)
        # ID cursors cannot be combined with time bounds; retain the date filter locally.
        params = {
            "status": "all", "limit": _PAGE_SIZE, "nested": "false",
            "before_order_id": last_id,
        }


def _date_bounds(start_date: str, end_date: str) -> tuple[datetime, datetime]:
    if any(re.fullmatch(r"(?:\d{8}|\d{4}-\d{2}-\d{2})", value) is None for value in (start_date, end_date)):
        raise BrokerRequestError("Alpaca order history date invalid")
    try:
        start = datetime.combine(date.fromisoformat(start_date), time.min, _EASTERN)
        end = datetime.combine(date.fromisoformat(end_date) + timedelta(days=1), time.min, _EASTERN)
    except (ValueError, OverflowError) as exc:
        raise BrokerRequestError("Alpaca order history date invalid") from exc
    if start >= end or start.date() == date.min:
        raise BrokerRequestError("Alpaca order history date range invalid")
    return start, end


def _parse_history(raw: JsonValue) -> tuple[str, datetime | None, AlpacaOrderHistory | None]:
    if not isinstance(raw, dict):
        raise BrokerRequestError("Alpaca order history row invalid")
    order_id, symbol, side = raw.get("id"), raw.get("symbol"), raw.get("side")
    status = raw.get("status", "")
    if (
        not isinstance(order_id, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", order_id) is None
        or not isinstance(symbol, str) or re.fullmatch(r"[A-Z][A-Z0-9./-]{0,31}", symbol) is None
        or not isinstance(side, str) or side not in {"buy", "sell"}
        or not isinstance(status, str) or status not in _STATUSES
    ):
        raise BrokerRequestError("Alpaca order history identity or status invalid")
    submitted_at = _submission_time(raw.get("submitted_at"))
    filled = _number(raw.get("filled_qty"))
    raw_price = raw.get("filled_avg_price")
    price = 0.0 if raw_price is None and filled == 0 else _number(raw_price)
    if filled < 0 or price < 0 or (filled > 0 and price <= 0):
        raise BrokerRequestError("Alpaca order history fill invalid")
    raw_quantity = raw.get("qty")
    if raw_quantity is None:
        if _number(raw.get("notional")) <= 0:
            raise BrokerRequestError("Alpaca order history notional invalid")
        if filled == 0 and status not in {"filled", "canceled", "expired", "rejected"}:
            return order_id, submitted_at, None
        # Known executed shares do not establish a notional order's requested shares.
        quantity = filled
    else:
        quantity = _number(raw_quantity)
    if (raw_quantity is not None and quantity <= 0) or filled > quantity:
        raise BrokerRequestError("Alpaca order history quantity invalid")
    return order_id, submitted_at, AlpacaOrderHistory(
        order_id, symbol, side, quantity, filled, price, status, submitted_at,
        requested_quantity_known=raw_quantity is not None,
    )


def _number(raw: JsonValue) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
        raise BrokerRequestError("Alpaca order history number invalid")
    try:
        result = float(raw)
    except (ValueError, OverflowError) as exc:
        raise BrokerRequestError("Alpaca order history number invalid") from exc
    if not isfinite(result):
        raise BrokerRequestError("Alpaca order history number invalid")
    return result


def _submission_time(raw: JsonValue) -> datetime | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})", raw,
    ) is None:
        raise BrokerRequestError("Alpaca order history submission time invalid")
    try:
        submitted_at = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise BrokerRequestError("Alpaca order history submission time invalid") from exc
    return submitted_at
