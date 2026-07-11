from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

from .models import AccountSnapshot, Position

JsonObject = dict[str, Any]
CliResult = dict[str, Any]


class BlockedCliOutput(TypedDict):
    status: Literal["blocked"]
    reason: str
    submitted_order: bool


@runtime_checkable
class KISBuyingPowerClient(Protocol):
    def get_latest_price(self, symbol: str) -> float: ...

    def get_overseas_buying_power(
        self,
        symbol: str,
        order_price: float | None = None,
    ) -> float: ...

    def get_account(self, refresh: bool = False) -> AccountSnapshot: ...

    def list_positions(self, refresh: bool = False) -> Mapping[str, Position]: ...


class CliCommandError(ValueError):
    pass
