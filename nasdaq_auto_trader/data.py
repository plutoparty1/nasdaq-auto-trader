"""CSV loading utilities for historical OHLCV bars."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .models import Bar


@dataclass(frozen=True, slots=True)
class MissingCsvColumnsError(ValueError):
    missing_columns: tuple[str, ...]

    def __str__(self) -> str:
        return f"missing CSV columns: {', '.join(self.missing_columns)}"


def load_bars_csv(path: str | Path) -> dict[str, list[Bar]]:
    """Load a CSV with symbol,timestamp,open,high,low,close,volume columns."""

    bars_by_symbol: dict[str, list[Bar]] = defaultdict(list)
    with Path(path).open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise MissingCsvColumnsError(tuple(sorted(missing)))

        for row in reader:
            symbol = row["symbol"].upper()
            bars_by_symbol[symbol].append(
                Bar(
                    symbol=symbol,
                    timestamp=row["timestamp"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )

    return {
        symbol: sorted(bars, key=lambda bar: bar.timestamp)
        for symbol, bars in bars_by_symbol.items()
    }
