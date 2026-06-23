"""CSV 파일을 읽어 백테스트용 봉 데이터로 바꾼다."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .models import Bar


def load_bars_csv(path: str | Path) -> dict[str, list[Bar]]:
    """symbol,timestamp,open,high,low,close,volume 컬럼 CSV를 읽는다."""

    bars_by_symbol: dict[str, list[Bar]] = defaultdict(list)
    with Path(path).open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing CSV columns: {', '.join(sorted(missing))}")

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
