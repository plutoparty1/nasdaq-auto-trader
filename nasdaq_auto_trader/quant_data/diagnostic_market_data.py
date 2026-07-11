from __future__ import annotations

import json
import math
from pathlib import Path

from nasdaq_auto_trader.models import Bar


class DiagnosticFixtureError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class DiagnosticMarketData:
    def __init__(self, bars_by_symbol: dict[str, list[Bar]]) -> None:
        self.bars_by_symbol = bars_by_symbol

    @classmethod
    def from_file(cls, path: Path) -> DiagnosticMarketData:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise DiagnosticFixtureError("diagnostic_bars_invalid") from exc
        if not isinstance(payload, dict) or not 1 <= len(payload) <= 120:
            raise DiagnosticFixtureError("diagnostic_bars_invalid")
        bars_by_symbol = {
            symbol: _parse_symbol_bars(symbol, raw_bars)
            for symbol, raw_bars in payload.items()
            if isinstance(symbol, str)
        }
        if len(bars_by_symbol) != len(payload):
            raise DiagnosticFixtureError("diagnostic_bars_invalid")
        return cls(bars_by_symbol)

    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        del timeframe, start, end
        return {
            symbol: self.bars_by_symbol[symbol][-limit:]
            for symbol in symbols
            if symbol in self.bars_by_symbol
        }


def _parse_symbol_bars(symbol: str, payload) -> list[Bar]:
    if not isinstance(payload, list) or not 20 <= len(payload) <= 2000:
        raise DiagnosticFixtureError("diagnostic_bars_invalid")
    bars = [_parse_bar(symbol, item) for item in payload]
    if len({item.timestamp for item in bars}) != len(bars):
        raise DiagnosticFixtureError("diagnostic_bars_invalid")
    return bars


def _parse_bar(symbol: str, payload) -> Bar:
    if not isinstance(payload, dict) or payload.get("symbol") != symbol:
        raise DiagnosticFixtureError("diagnostic_bars_invalid")
    try:
        timestamp = str(payload["timestamp"]).strip()
        values = tuple(
            float(payload[name])
            for name in ("open", "high", "low", "close", "volume")
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise DiagnosticFixtureError("diagnostic_bars_invalid") from exc
    if not timestamp or not all(math.isfinite(value) for value in values):
        raise DiagnosticFixtureError("diagnostic_bars_invalid")
    open_price, high, low, close, volume = values
    if min(open_price, high, low, close) <= 0 or volume < 0:
        raise DiagnosticFixtureError("diagnostic_bars_invalid")
    if high < max(open_price, low, close) or low > min(open_price, high, close):
        raise DiagnosticFixtureError("diagnostic_bars_invalid")
    return Bar(symbol, timestamp, open_price, high, low, close, volume)
