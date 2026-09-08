"""CSV loading utilities for historical OHLCV bars."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import TextIO

from .models import Bar


@dataclass(frozen=True, slots=True)
class MissingCsvColumnsError(ValueError):
    missing_columns: tuple[str, ...]

    def __str__(self) -> str:
        return f"missing CSV columns: {', '.join(self.missing_columns)}"


@dataclass(frozen=True, slots=True)
class InvalidCsvDataError(ValueError):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class CsvFileError(OSError):
    path: Path

    def __str__(self) -> str:
        return f"CSV file could not be opened: {self.path}"


def load_bars_csv(path: str | Path) -> dict[str, list[Bar]]:
    """Load a CSV with symbol,timestamp,open,high,low,close,volume columns."""

    bars_by_symbol: dict[str, list[Bar]] = defaultdict(list)
    seen_keys: set[tuple[str, str]] = set()
    with _open_csv(Path(path)) as file:
        reader = csv.DictReader(file)
        required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise MissingCsvColumnsError(tuple(sorted(missing)))

        for row in reader:
            symbol = (row["symbol"] or "").strip().upper()
            if not symbol:
                raise InvalidCsvDataError("symbol must not be blank")
            timestamp = _parse_timestamp(row["timestamp"])
            key = (symbol, timestamp)
            if key in seen_keys:
                raise InvalidCsvDataError(
                    f"duplicate symbol and timestamp: {symbol}, {timestamp}"
                )
            seen_keys.add(key)
            open_price = _parse_price("open", row["open"])
            high_price = _parse_price("high", row["high"])
            low_price = _parse_price("low", row["low"])
            close_price = _parse_price("close", row["close"])
            if high_price < max(open_price, low_price, close_price):
                raise InvalidCsvDataError(
                    "high must be greater than or equal to open, low, and close"
                )
            if low_price > min(open_price, high_price, close_price):
                raise InvalidCsvDataError(
                    "low must be less than or equal to open, high, and close"
                )
            bars_by_symbol[symbol].append(
                Bar(
                    symbol=symbol,
                    timestamp=timestamp,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=_parse_number("volume", row["volume"], minimum=0.0),
                )
            )

    if not bars_by_symbol:
        raise InvalidCsvDataError("CSV must contain at least one bar")

    return {
        symbol: sorted(bars, key=lambda bar: bar.timestamp)
        for symbol, bars in bars_by_symbol.items()
    }


def _open_csv(path: Path) -> TextIO:
    try:
        return path.open("r", encoding="utf-8-sig", newline="")
    except OSError as error:
        raise CsvFileError(path) from error


def _parse_timestamp(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        raise InvalidCsvDataError("timestamp must not be blank")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidCsvDataError("timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _parse_price(name: str, value: str | None) -> float:
    parsed = _parse_number(name, value)
    if parsed <= 0:
        raise InvalidCsvDataError(f"{name} must be greater than zero")
    return parsed


def _parse_number(
    name: str,
    value: str | None,
    minimum: float | None = None,
) -> float:
    try:
        parsed = float((value or "").strip())
    except ValueError as exc:
        raise InvalidCsvDataError(f"{name} must be a number") from exc
    if not isfinite(parsed):
        raise InvalidCsvDataError(f"{name} must be a finite number")
    if minimum is not None and parsed < minimum:
        raise InvalidCsvDataError(f"{name} must be greater than or equal to {minimum}")
    return parsed
