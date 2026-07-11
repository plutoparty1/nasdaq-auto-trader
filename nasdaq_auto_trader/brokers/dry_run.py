from __future__ import annotations

from ..models import OrderRequest
from .common import JsonObject


class DryRunBroker:
    """Record orders in memory instead of sending them to a broker."""

    def __init__(self) -> None:
        self.orders: list[OrderRequest] = []

    def submit_order(self, order: OrderRequest) -> JsonObject:
        """Record an order and return a broker-like response."""

        self.orders.append(order)
        return {"status": "dry_run", "order": order.to_alpaca_payload()}
