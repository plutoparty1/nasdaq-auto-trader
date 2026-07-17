from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit
from urllib.request import Request

from .broker import KISCredentials
from .brokers.common import BrokerRequestError, JsonObject
from .brokers.kis_client import KISClient
from .brokers.kis_reconciliation import KISOpenOrder
from .live_canary_policy import CANARY_POLICY
from .models import AccountSnapshot, Position


class PreflightClient(Protocol):
    def get_account(self, refresh: bool = False) -> AccountSnapshot: ...

    def list_positions(self, refresh: bool = False) -> dict[str, Position]: ...

    def list_open_orders(self) -> tuple[KISOpenOrder, ...]: ...


class KISPreflightTransportClient(KISClient):
    _ALLOWED_TRANSPORT = frozenset(
        {
            ("POST", "/oauth2/tokenP"),
            ("GET", "/uapi/overseas-stock/v1/trading/inquire-present-balance"),
            ("GET", "/uapi/overseas-stock/v1/trading/inquire-balance"),
            ("GET", "/uapi/overseas-stock/v1/trading/inquire-nccs"),
        }
    )

    def __init__(self, credentials: KISCredentials) -> None:
        super().__init__(credentials)

    def _open_json(self, request: Request, label: str) -> JsonObject:
        endpoint = (request.get_method().upper(), urlsplit(request.full_url).path)
        if endpoint not in self._ALLOWED_TRANSPORT:
            raise BrokerRequestError("preflight_transport_not_allowed")
        payload = super()._open_json(request, label)
        if not isinstance(payload, dict):
            raise BrokerRequestError("preflight_transport_payload_invalid")
        return payload


@dataclass(frozen=True, slots=True)
class ReadOnlyPreflightClient:
    """Expose only the account reads required by canary preflight."""

    _client: PreflightClient

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        return self._client.get_account(refresh=refresh)

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        return self._client.list_positions(refresh=refresh)

    def list_open_orders(self) -> tuple[KISOpenOrder, ...]:
        return self._client.list_open_orders()


@dataclass(frozen=True, slots=True)
class PreflightResult:
    ready: bool
    cash_gate_met: bool
    position_count: int
    open_order_count: int
    blockers: tuple[str, ...]


def run_preflight(client: PreflightClient) -> PreflightResult:
    account = client.get_account(refresh=True)
    positions = client.list_positions(refresh=True)
    open_orders = client.list_open_orders()
    cash_gate_met = account.cash >= float(CANARY_POLICY.total_cash_gate_usd)
    blockers: list[str] = []
    if positions:
        blockers.append("existing_position")
    if open_orders:
        blockers.append("existing_open_order")
    if not cash_gate_met:
        blockers.append("cash_below_canary_gate")
    return PreflightResult(
        ready=not blockers,
        cash_gate_met=cash_gate_met,
        position_count=len(positions),
        open_order_count=len(open_orders),
        blockers=tuple(blockers),
    )
