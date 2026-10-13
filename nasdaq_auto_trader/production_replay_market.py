from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import final

from .ai_quant_lab.types import JsonObject
from .broker import KISCredentials
from .brokers.kis_order import KISOrderMixin
from .brokers.kis_reconciliation import KISOrderHistory
from .live_canary_identity import account_fingerprint
from .models import AccountSnapshot, Bar, Position


@dataclass(frozen=True, slots=True)
class ReplayOpenOrder:
    symbol: str
    side: str


@dataclass(frozen=True, slots=True)
class ReplayFill:
    order_id: str
    symbol: str
    side: str
    quantity: float
    filled_quantity: float
    average_fill_price: float
    status: str
    submitted_at: datetime


@final
class ReplayMarket(KISOrderMixin):
    def __init__(self, directory: Path, credentials: KISCredentials) -> None:
        self.credentials = credentials
        self.account_fingerprint = account_fingerprint(credentials.account_no, credentials.account_product_code)
        self._broker_lease_path = directory / "fake-account.lease"
        self._broker_live_lease = None
        self.account = AccountSnapshot(1000, 1000, 1000)
        self.positions: dict[str, Position] = {}
        self.pending: tuple[ReplayOpenOrder, ...] = ()
        self.history: tuple[KISOrderHistory, ...] = ()
        self.requests: list[JsonObject] = []
        self.response: JsonObject = {"status": "accepted", "id": "test-only-1"}
        self.rising = True
        self.latest_day = datetime(2026, 10, 12, 20, tzinfo=UTC)
        self.bar_requests = 0
        self.history_requests = 0
        self.open_order_requests = 0
        self.last_order_qty = ""
        self.price = 20.61
        self.price_step = .04

    def get_stock_bars(self, symbols: list[str], timeframe: str, start: str,
                       end: str | None = None, limit: int = 1000) -> dict[str, list[Bar]]:
        del timeframe, start, end, limit
        self.bar_requests += 1
        if "CMCSA" not in symbols:
            return {}
        dates: list[datetime] = []
        day = self.latest_day
        while len(dates) < 140:
            if day.weekday() < 5:
                dates.append(day)
            day -= timedelta(days=1)
        return {"CMCSA": [Bar("CMCSA", timestamp.isoformat(), price, price + .02,
                              price - .02, price, 1_000_000)
                           for index, timestamp in enumerate(reversed(dates))
                           for price in [self.price - (139 - index) * self.price_step if self.rising
                                         else self.price + (139 - index) * self.price_step]]}

    def get_latest_quotes(self, symbols: list[str]) -> dict[str, JsonObject]:
        return {symbol: {"bp": self.price - .01, "ap": self.price} for symbol in symbols if symbol == "CMCSA"}

    def get_latest_price(self, symbol: str) -> float:
        del symbol
        return self.price

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        del refresh
        return self.account

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        del refresh
        return self.positions

    def get_overseas_buying_power(self, symbol: str, limit_price: float) -> float:
        del symbol, limit_price
        return self.account.buying_power

    def list_open_orders(self) -> tuple[ReplayOpenOrder, ...]:
        self.open_order_requests += 1
        return self.pending

    def list_order_history(self, start_date: str, end_date: str) -> tuple[KISOrderHistory, ...]:
        del start_date, end_date
        self.history_requests += 1
        return self.history

    def _request(self, method: str, path: str, *, tr_id: str, body: JsonObject) -> JsonObject:
        if method != "POST" or path != "/uapi/overseas-stock/v1/trading/order":
            raise AssertionError("unexpected_fake_kis_request")
        self.requests.append({"method": method, "path": path, "tr_id": tr_id, "body": body})
        self.last_order_qty = str(body["ORD_QTY"])
        return self.response
