from __future__ import annotations

import json
import re
from dataclasses import dataclass
from math import isfinite
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request

from ..models import AccountSnapshot, Bar, OrderRequest, Position
from .alpaca_history import AlpacaOrderHistory, read_order_history
from .common import (
    BrokerCredentialError,
    BrokerOrderError,
    BrokerRequestError,
    JsonObject,
)
from .common import broker_urlopen as urlopen


@dataclass(frozen=True, slots=True)
class AlpacaCredentials:
    """Alpaca credentials and data-feed preferences."""

    api_key: str
    secret_key: str
    paper: bool = True
    feed: str = "iex"
    timeout: int = 30


@dataclass(frozen=True, slots=True)
class AlpacaOpenOrder:
    symbol: str
    side: str


class AlpacaClient:
    """Minimal Alpaca client for account, position, order, and stock-bar APIs."""

    trading_paper_base_url = "https://paper-api.alpaca.markets"
    trading_live_base_url = "https://api.alpaca.markets"
    data_base_url = "https://data.alpaca.markets"

    def __init__(self, credentials: AlpacaCredentials) -> None:
        if not credentials.api_key or not credentials.secret_key:
            raise BrokerCredentialError("Alpaca API key and secret key are required")
        self.credentials = credentials
        self.trading_base_url = (
            self.trading_paper_base_url
            if credentials.paper
            else self.trading_live_base_url
        )

    def get_account(self) -> AccountSnapshot:
        """Return cash, equity, and buying power from Alpaca."""

        payload = self._request("GET", self.trading_base_url, "/v2/account")
        return AccountSnapshot(
            cash=float(payload["cash"]),
            equity=float(payload["equity"]),
            buying_power=float(payload["buying_power"]),
        )

    def list_positions(self) -> dict[str, Position]:
        """Return open Alpaca positions keyed by symbol."""

        payload = self._request("GET", self.trading_base_url, "/v2/positions")
        positions: dict[str, Position] = {}
        for item in payload:
            symbol = str(item["symbol"])
            positions[symbol] = Position(
                symbol=symbol,
                qty=float(item["qty"]),
                market_value=float(item["market_value"]),
                avg_entry_price=float(item["avg_entry_price"]),
            )
        return positions

    def list_open_orders(self) -> tuple[AlpacaOpenOrder, ...]:
        payload = self._request(
            "GET", self.trading_base_url, "/v2/orders",
            {"status": "open", "limit": 500, "nested": "false"},
        )
        if not isinstance(payload, list) or len(payload) >= 500:
            raise BrokerRequestError("Alpaca open orders incomplete or invalid")
        orders: list[AlpacaOpenOrder] = []
        for item in payload:
            if not isinstance(item, dict):
                raise BrokerRequestError("Alpaca open order invalid")
            symbol = item.get("symbol")
            side = item.get("side")
            if (
                not isinstance(symbol, str)
                or re.fullmatch(r"[A-Z][A-Z0-9./-]{0,31}", symbol) is None
                or side not in ("buy", "sell")
            ):
                raise BrokerRequestError("Alpaca open order identity invalid")
            raw_quantity = item.get("qty")
            try:
                amount = float(str(
                    raw_quantity if raw_quantity is not None else item.get("notional")
                ))
                filled = float(str(item.get("filled_qty", "0")))
            except (ValueError, OverflowError) as exc:
                raise BrokerRequestError("Alpaca open order quantity invalid") from exc
            if (
                not isfinite(amount) or amount <= 0
                or not isfinite(filled) or filled < 0
                or (raw_quantity is not None and filled > amount)
            ):
                raise BrokerRequestError("Alpaca open order quantity invalid")
            orders.append(AlpacaOpenOrder(symbol, side))
        return tuple(orders)

    def submit_order(self, order: OrderRequest) -> JsonObject:
        """Submit one risk-approved order to Alpaca."""

        if order.side == "buy":
            required_cash = self._required_buy_cash(order)
            account = self.get_account()
            if not isfinite(account.cash) or account.cash < required_cash:
                raise BrokerOrderError("Alpaca buy exceeds deposited cash")
            if not isfinite(account.buying_power) or account.buying_power < required_cash:
                raise BrokerOrderError("Alpaca buy exceeds buying power")
        return self._request(
            "POST",
            self.trading_base_url,
            "/v2/orders",
            body=order.to_alpaca_payload(),
        )

    def list_order_history(self, start_date: str, end_date: str) -> tuple[AlpacaOrderHistory, ...]:
        return read_order_history(self, start_date, end_date)

    @staticmethod
    def _required_buy_cash(order: OrderRequest) -> float:
        if order.notional is not None and isfinite(order.notional) and order.notional > 0:
            return order.notional
        if (
            order.qty is not None
            and order.limit_price is not None
            and isfinite(order.qty)
            and isfinite(order.limit_price)
            and order.qty > 0
            and order.limit_price > 0
        ):
            return order.qty * order.limit_price
        raise BrokerOrderError(
            "Alpaca cash-only buy requires positive notional or quantity with limit price"
        )

    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        """Fetch historical stock bars, following Alpaca pagination."""

        bars: dict[str, list[Bar]] = {symbol: [] for symbol in symbols}
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "symbols": ",".join(symbols),
                "timeframe": timeframe,
                "start": start,
                "limit": limit,
                "feed": self.credentials.feed,
                "adjustment": "all",
                "sort": "asc",
            }
            if end is not None:
                params["end"] = end
            if page_token is not None:
                params["page_token"] = page_token

            payload = self._request("GET", self.data_base_url, "/v2/stocks/bars", params)
            for symbol, raw_bars in payload.get("bars", {}).items():
                bars.setdefault(symbol, []).extend(
                    Bar.from_alpaca(symbol, raw_bar) for raw_bar in raw_bars
                )
            page_token = payload.get("next_page_token")
            if not page_token:
                break
        return bars

    def get_latest_quotes(self, symbols: list[str]) -> dict[str, JsonObject]:
        payload = self._request(
            "GET",
            self.data_base_url,
            "/v2/stocks/snapshots",
            {
                "symbols": ",".join(symbols),
                "feed": self.credentials.feed,
            },
        )
        if not isinstance(payload, dict):
            raise BrokerRequestError("Alpaca snapshot response invalid")
        quotes: dict[str, JsonObject] = {}
        for symbol in symbols:
            snapshot = payload.get(symbol)
            if not isinstance(snapshot, dict):
                raise BrokerRequestError(f"Alpaca snapshot missing for {symbol}")
            quote = snapshot.get("latestQuote")
            if not isinstance(quote, dict):
                raise BrokerRequestError(f"Alpaca latest quote missing for {symbol}")
            quotes[symbol] = quote
        return quotes

    def _request(
        self,
        method: str,
        base_url: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        """Send one HTTP request and decode its JSON response."""

        query = f"?{urlencode(params)}" if params else ""
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            f"{base_url}{path}{query}",
            data=data,
            method=method,
            headers={
                "APCA-API-KEY-ID": self.credentials.api_key,
                "APCA-API-SECRET-KEY": self.credentials.secret_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.credentials.timeout) as response:
                text = response.read().decode("utf-8")
        except HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace")
            raise BrokerRequestError(
                f"Alpaca API error {exc.code}: {error_text}"
            ) from exc

        if not text:
            return {}
        return json.loads(text)
