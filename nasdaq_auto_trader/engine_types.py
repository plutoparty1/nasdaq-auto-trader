from __future__ import annotations

from typing import Any, Protocol

from .models import Bar, OrderRequest


JsonObject = dict[str, Any]
BrokerResponsePayload = dict[str, Any]
DecisionPayload = dict[str, Any]
EngineCycleItem = dict[str, Any]


class BrokerLike(Protocol):
    """Minimal broker behavior required by the engine."""

    def submit_order(self, order: OrderRequest) -> BrokerResponsePayload:
        """Submit one order."""


class MarketDataLike(Protocol):
    """Minimal market-data behavior required by the engine."""

    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        """Return historical bars by symbol."""
