from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .ai_quant_lab.types import JsonObject, JsonValue
from .brokers.common import BrokerRequestError
from .models import Bar
from .quant_data.features import PriceBar

if TYPE_CHECKING:
    from .automatic_selection import AutomaticSelectionRequest


class SelectionMarketData(Protocol):
    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]: ...


@runtime_checkable
class KISLiquidityMarketData(Protocol):
    def get_liquid_overseas_symbols(
        self,
        universe: set[str],
        limit: int = 30,
    ) -> tuple[str, ...]: ...


@runtime_checkable
class BatchQuoteMarketData(Protocol):
    def get_latest_quotes(self, symbols: list[str]) -> dict[str, JsonObject]: ...


@runtime_checkable
class BestQuoteMarketData(Protocol):
    def get_best_quote(self, symbol: str) -> JsonObject: ...


@dataclass(frozen=True, slots=True)
class EntryMarketData:
    bars_by_symbol: dict[str, list[Bar]]
    quotes_by_symbol: dict[str, tuple[float, float]]
    warnings: tuple[str, ...]


def load_entry_market_data(
    request: AutomaticSelectionRequest,
    symbols: list[str],
) -> EntryMarketData:
    bars_by_symbol: dict[str, list[Bar]] = {}
    quotes_by_symbol: dict[str, tuple[float, float]] = {}
    warnings: list[str] = []
    for symbol in symbols:
        try:
            bars = _load_bars(request, [symbol]).get(symbol, [])
        except (BrokerRequestError, OSError):
            warnings.append(f"entry_market_bars_unavailable:{symbol}")
            continue
        if not bars:
            warnings.append(f"entry_market_bars_missing:{symbol}")
            continue
        try:
            quotes = _load_quotes(request, [symbol])
        except (BrokerRequestError, OSError):
            warnings.append(f"entry_market_quote_unavailable:{symbol}")
            continue
        bars_by_symbol[symbol] = bars
        quotes_by_symbol.update(quotes)
    return EntryMarketData(bars_by_symbol, quotes_by_symbol, tuple(warnings))


def _load_bars(
    request: AutomaticSelectionRequest,
    symbols: list[str],
) -> dict[str, list[Bar]]:
    config = request.config
    now = request.now
    start = now - timedelta(days=config.lookback_days)
    return dict(
        request.market_data.get_stock_bars(
            symbols,
            config.timeframe,
            start.date().isoformat(),
            now.date().isoformat(),
            config.bar_limit,
        )
    )


def _load_quotes(
    request: AutomaticSelectionRequest,
    symbols: list[str],
) -> dict[str, tuple[float, float]]:
    config = request.config
    market_data = request.market_data
    if config.mode == "dry_run":
        return {}
    if isinstance(market_data, BatchQuoteMarketData):
        return _parsed_quotes(symbols, market_data.get_latest_quotes(symbols))
    if isinstance(market_data, BestQuoteMarketData):
        return _parsed_quotes(
            symbols,
            {symbol: market_data.get_best_quote(symbol) for symbol in symbols},
        )
    raise BrokerRequestError("market_quote_provider_unavailable")


def _parsed_quotes(
    symbols: list[str],
    payloads: dict[str, JsonObject],
) -> dict[str, tuple[float, float]]:
    if set(payloads) != set(symbols):
        raise BrokerRequestError("market_quote_batch_incomplete")
    return {
        symbol: _quote_prices(payloads[symbol])
        for symbol in symbols
    }


def _quote_prices(payload: JsonObject) -> tuple[float, float]:
    bid = _first_number(payload, ("bp", "pbid1", "bid"))
    ask = _first_number(payload, ("ap", "pask1", "ask"))
    if bid <= 0 or ask < bid:
        raise BrokerRequestError("market_quote_invalid")
    return bid, ask


def _first_number(payload: JsonObject, keys: tuple[str, ...]) -> float:
    for key in keys:
        value: JsonValue | None = payload.get(key)
        if value in (None, ""):
            continue
        try:
            number = float(str(value).replace(",", ""))
        except ValueError:
            continue
        if math.isfinite(number):
            return number
    return 0.0


def _price_bar(bar: Bar) -> PriceBar:
    return PriceBar(
        symbol=bar.symbol,
        timestamp=bar.timestamp,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
    )
