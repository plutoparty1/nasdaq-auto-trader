from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final, final

from .engine_types import MarketDataLike
from .models import Bar
from .quant_data.feature_statistics import normalized_timestamps

MAX_HISTORY_PAGES: Final = 20


@dataclass(frozen=True, slots=True)
class LearningHistoryWindow:
    timeframe: str
    start: date
    end: date
    limit: int


@final
class LearningHistoryError(ValueError):
    def __init__(self, reason: str, symbol: str = '') -> None:
        self.reason = reason
        self.symbol = symbol
        super().__init__(f'{reason}: {symbol}' if symbol else reason)


def collect_learning_history(
    market_data: MarketDataLike,
    symbols: list[str],
    window: LearningHistoryWindow,
) -> dict[str, list[Bar]]:
    """Extend capped daily responses backwards without changing the broker adapter."""
    if window.timeframe != '1Day' or window.start > window.end or window.limit < 1:
        raise LearningHistoryError('learning_history_window_invalid')
    initial = market_data.get_stock_bars(
        symbols, window.timeframe, window.start.isoformat(),
        end=window.end.isoformat(), limit=window.limit,
    )
    collected: dict[str, list[Bar]] = {}
    for symbol in symbols:
        observations: dict[datetime, Bar] = {}
        page = initial.get(symbol, [])
        cursor = window.end
        for page_index in range(MAX_HISTORY_PAGES):
            if not page:
                break
            oldest = _merge_page(observations, page, symbol)
            if oldest > cursor:
                raise LearningHistoryError('learning_history_cursor_not_advancing', symbol)
            eligible = [stamp for stamp in observations if window.start <= stamp.date() <= window.end]
            if len(eligible) >= window.limit or oldest <= window.start:
                break
            if page_index + 1 == MAX_HISTORY_PAGES:
                raise LearningHistoryError('learning_history_page_limit', symbol)
            cursor = oldest - timedelta(days=1)
            page = market_data.get_stock_bars(
                [symbol], window.timeframe, window.start.isoformat(),
                end=cursor.isoformat(), limit=window.limit - len(eligible),
            ).get(symbol, [])
        collected[symbol] = [
            observations[stamp] for stamp in sorted(observations)
            if window.start <= stamp.date() <= window.end
        ][-window.limit:]
    return collected


def _merge_page(observations: dict[datetime, Bar], page: list[Bar], symbol: str) -> date:
    stamps = normalized_timestamps(page)
    if stamps is None:
        raise LearningHistoryError('learning_history_timestamp_invalid', symbol)
    for stamp, bar in zip(stamps, page, strict=True):
        if bar.symbol != symbol:
            raise LearningHistoryError('learning_history_symbol_mismatch', symbol)
        previous = observations.get(stamp)
        if previous is not None and (
            previous.open, previous.high, previous.low, previous.close, previous.volume
        ) != (bar.open, bar.high, bar.low, bar.close, bar.volume):
            raise LearningHistoryError('learning_history_duplicate_conflict', symbol)
        observations[stamp] = bar
    return min(stamps).date()
