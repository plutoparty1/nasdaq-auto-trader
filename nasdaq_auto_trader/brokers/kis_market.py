from __future__ import annotations

from datetime import datetime, timezone

from ..models import Bar
from .common import (
    BrokerOrderError,
    BrokerRequestError,
    JsonObject,
    _compact_date,
    _first_float,
    _first_output_dict,
)


class KISMarketDataMixin:
    def get_liquid_overseas_symbols(
        self,
        universe: set[str],
        limit: int = 30,
    ) -> tuple[str, ...]:
        if (
            self.credentials.price_exchange_code != "NAS"
            or self.credentials.order_exchange_code != "NASD"
        ):
            raise BrokerRequestError("kis_exchange_identity_mismatch")
        if limit < 1 or limit > 30:
            raise BrokerRequestError("kis_liquidity_limit_invalid")
        payload = self._request(
            "GET",
            "/uapi/overseas-stock/v1/ranking/trade-vol",
            tr_id="HHDFS76310010",
            params={
                "AUTH": "",
                "EXCD": "NAS",
                "NDAY": "0",
                "VOL_RANG": "0",
                "PRC1": "",
                "PRC2": "",
                "KEYB": "",
            },
        )
        rows = payload.get("output2")
        if not isinstance(rows, list):
            raise BrokerRequestError("kis_liquidity_response_invalid")
        symbols: list[str] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise BrokerRequestError("kis_liquidity_response_invalid")
            raw_symbol = row.get("symb")
            if not isinstance(raw_symbol, str) or not raw_symbol.strip():
                raise BrokerRequestError("kis_liquidity_response_invalid")
            symbol = raw_symbol.strip().upper()
            if symbol in seen:
                raise BrokerRequestError("kis_liquidity_response_duplicate")
            seen.add(symbol)
            if symbol in universe:
                symbols.append(symbol)
            if len(symbols) == limit:
                break
        return tuple(symbols)

    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        """Fetch KIS overseas daily bars for configured symbols."""

        if timeframe != "1Day":
            raise BrokerOrderError("KISClient currently supports timeframe='1Day' only")
        end_date = _compact_date(end) if end else datetime.now(timezone.utc).strftime("%Y%m%d")
        bars: dict[str, list[Bar]] = {}
        for symbol in symbols:
            payload = self._request(
                "GET",
                "/uapi/overseas-price/v1/quotations/dailyprice",
                tr_id="HHDFS76240000",
                params={
                    "AUTH": "",
                    "EXCD": self.credentials.price_exchange_code,
                    "SYMB": symbol,
                    "GUBN": "0",
                    "BYMD": end_date,
                    "MODP": "1",
                },
            )
            rows = payload.get("output2") or payload.get("output") or []
            if isinstance(rows, dict):
                rows = [rows]
            parsed = [self._bar_from_dailyprice(symbol, item) for item in rows]
            parsed = [bar for bar in parsed if bar is not None]
            parsed.sort(key=lambda bar: bar.timestamp)
            bars[symbol] = parsed[-limit:]
        return bars

    def get_latest_price(self, symbol: str) -> float:
        """Return the latest KIS overseas stock price."""

        payload = self._request(
            "GET",
            "/uapi/overseas-price/v1/quotations/price",
            tr_id="HHDFS00000300",
            params={
                "AUTH": "",
                "EXCD": self.credentials.price_exchange_code,
                "SYMB": symbol,
            },
        )
        output = payload.get("output") or {}
        if isinstance(output, list):
            output = output[0] if output else {}
        price = _first_float(output, "last", "ovrs_nmix_prpr", "stck_prpr", "clos")
        if price <= 0:
            raise BrokerRequestError(f"KIS latest price missing for {symbol}")
        return price

    def get_price_detail(self, symbol: str) -> JsonObject:
        """Return KIS overseas current-price detail fields for one symbol."""

        payload = self._request(
            "GET",
            "/uapi/overseas-price/v1/quotations/price-detail",
            tr_id="HHDFS76200200",
            params={
                "AUTH": "",
                "EXCD": self.credentials.price_exchange_code,
                "SYMB": symbol,
            },
        )
        return _first_output_dict(payload, "output")

    def get_best_quote(self, symbol: str) -> JsonObject:
        """Return KIS overseas best bid/ask quote fields for one symbol."""

        payload = self._request(
            "GET",
            "/uapi/overseas-price/v1/quotations/inquire-asking-price",
            tr_id="HHDFS76200100",
            params={
                "AUTH": "",
                "EXCD": self.credentials.price_exchange_code,
                "SYMB": symbol,
            },
        )
        summary = _first_output_dict(payload, "output1")
        quote = _first_output_dict(payload, "output2")
        extra = _first_output_dict(payload, "output3")
        combined = dict(summary)
        combined.update(quote)
        combined.update(extra)
        return combined

    def _bar_from_dailyprice(self, symbol: str, payload: JsonObject) -> Bar | None:
        timestamp = str(
            payload.get("xymd")
            or payload.get("stck_bsop_date")
            or payload.get("date")
            or ""
        )
        if not timestamp:
            return None
        return Bar(
            symbol=symbol,
            timestamp=timestamp,
            open=_first_float(payload, "open", "ovrs_nmix_oprc", "stck_oprc"),
            high=_first_float(payload, "high", "ovrs_nmix_hgpr", "stck_hgpr"),
            low=_first_float(payload, "low", "ovrs_nmix_lwpr", "stck_lwpr"),
            close=_first_float(payload, "clos", "last", "ovrs_nmix_prpr", "stck_clpr"),
            volume=_first_float(payload, "tvol", "acml_vol", "volume", default=0.0),
        )
