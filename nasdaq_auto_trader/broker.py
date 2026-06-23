"""Alpaca API와 dry-run 주문 기록 브로커를 제공한다."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import AccountSnapshot, Bar, OrderRequest, Position


@dataclass(frozen=True)
class AlpacaCredentials:
    """Alpaca 접속에 필요한 키와 접속 모드를 담는다."""

    api_key: str
    secret_key: str
    paper: bool = True
    feed: str = "iex"
    timeout: int = 30


class DryRunBroker:
    """실제 주문을 보내지 않고 주문 내용을 메모리에만 기록한다."""

    def __init__(self) -> None:
        """테스트와 예행연습에 쓸 주문 목록을 준비한다."""

        self.orders: list[OrderRequest] = []

    def submit_order(self, order: OrderRequest) -> dict:
        """주문을 보내는 대신 기록하고 가짜 응답을 돌려준다."""

        self.orders.append(order)
        return {"status": "dry_run", "order": order.to_alpaca_payload()}


class AlpacaClient:
    """Alpaca 시세 조회와 주문 제출을 담당한다."""

    trading_paper_base_url = "https://paper-api.alpaca.markets"
    trading_live_base_url = "https://api.alpaca.markets"
    data_base_url = "https://data.alpaca.markets"

    def __init__(self, credentials: AlpacaCredentials) -> None:
        """자격 정보가 비어 있으면 바로 알려준다."""

        if not credentials.api_key or not credentials.secret_key:
            raise ValueError("Alpaca API key and secret key are required")
        self.credentials = credentials
        self.trading_base_url = (
            self.trading_paper_base_url
            if credentials.paper
            else self.trading_live_base_url
        )

    def get_account(self) -> AccountSnapshot:
        """계좌의 현금, 총자산, 매수 가능 금액을 가져온다."""

        payload = self._request("GET", self.trading_base_url, "/v2/account")
        return AccountSnapshot(
            cash=float(payload["cash"]),
            equity=float(payload["equity"]),
            buying_power=float(payload["buying_power"]),
        )

    def list_positions(self) -> dict[str, Position]:
        """현재 보유 중인 포지션을 종목별로 가져온다."""

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

    def submit_order(self, order: OrderRequest) -> dict:
        """위험관리를 통과한 주문을 Alpaca에 보낸다."""

        return self._request(
            "POST",
            self.trading_base_url,
            "/v2/orders",
            body=order.to_alpaca_payload(),
        )

    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        """Alpaca 주식 봉 데이터를 페이지 끝까지 가져온다."""

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

    def _request(
        self,
        method: str,
        base_url: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        """공통 HTTP 요청을 보내고 JSON 응답을 파이썬 값으로 바꾼다."""

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
            raise RuntimeError(f"Alpaca API error {exc.code}: {error_text}") from exc

        if not text:
            return {}
        return json.loads(text)
