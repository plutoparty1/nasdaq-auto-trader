from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta

from nasdaq_auto_trader.models import AccountSnapshot, Bar, Position


class DryRunMarketData:
    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
    ) -> Mapping[str, list[Bar]]:
        del timeframe, start
        count = max(70, min(limit, 260))
        latest_date = date.fromisoformat(end) if end else date.today()
        return {
            symbol: _flat_bars(symbol, count, latest_date)
            for symbol in symbols
        }

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        del refresh
        return AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000)

    def list_positions(self, refresh: bool = False) -> Mapping[str, Position]:
        del refresh
        return {}


def _flat_bars(symbol: str, count: int, latest_date: date) -> list[Bar]:
    return [
        Bar(
            symbol=symbol,
            timestamp=(latest_date - timedelta(days=count - index - 1)).isoformat(),
            open=100.0,
            high=100.5,
            low=99.5,
            close=100.0,
            volume=1_000_000,
        )
        for index in range(count)
    ]
