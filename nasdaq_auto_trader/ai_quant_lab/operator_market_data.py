from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import TypeAlias

from nasdaq_auto_trader.ai_quant_lab.types import JsonObject, JsonValue
from nasdaq_auto_trader.quant_data.features import PriceBar

BarsBySymbol: TypeAlias = dict[str, list[PriceBar]]


@dataclass(frozen=True, slots=True)
class BarsJsonError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


def load_bars_json(path: Path | None) -> BarsBySymbol:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BarsJsonError("bars_json_root_must_be_object")
    parsed: BarsBySymbol = {}
    for symbol, rows in payload.items():
        if not isinstance(symbol, str) or not isinstance(rows, list):
            raise BarsJsonError("bars_json_symbol_rows_invalid")
        parsed[symbol.upper()] = [_price_bar(symbol.upper(), row) for row in rows]
    return parsed


def _price_bar(symbol: str, value: JsonValue) -> PriceBar:
    if not isinstance(value, dict):
        raise BarsJsonError("bars_json_row_must_be_object")
    return PriceBar(
        symbol=symbol,
        timestamp=_text(value, "timestamp"),
        open=_number(value, "open"),
        high=_number(value, "high"),
        low=_number(value, "low"),
        close=_number(value, "close"),
        volume=_number(value, "volume"),
        bid=_number(value, "bid", default=0.0),
        ask=_number(value, "ask", default=0.0),
    )


def _text(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise BarsJsonError(f"bars_json_{key}_required")


def _number(payload: JsonObject, key: str, default: float | None = None) -> float:
    value = payload.get(key)
    if value is None and default is not None:
        return default
    if (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and isfinite(float(value))
    ):
        return float(value)
    raise BarsJsonError(f"bars_json_{key}_must_be_number")
