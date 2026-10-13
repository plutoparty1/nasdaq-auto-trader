from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import override

import pytest

from nasdaq_auto_trader import learning_history
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.learning_data import collect_completed_learning_bars
from nasdaq_auto_trader.learning_history import (
    LearningHistoryError,
    LearningHistoryWindow,
    collect_learning_history,
)
from nasdaq_auto_trader.models import Bar


class PagedHistory:
    def __init__(self, histories: dict[str, list[Bar]], page_size: int = 100) -> None:
        self.histories: dict[str, list[Bar]] = histories
        self.page_size: int = page_size
        self.calls: list[tuple[list[str], str, str | None, int]] = []

    def get_stock_bars(self, symbols: list[str], timeframe: str, start: str,
                       end: str | None = None, limit: int = 1000) -> dict[str, list[Bar]]:
        assert timeframe == '1Day'
        self.calls.append((symbols, start, end, limit))
        return {symbol: [bar for bar in self.histories.get(symbol, [])
                         if end is None or date.fromisoformat(bar.timestamp) <= date.fromisoformat(end)]
                [-min(self.page_size, limit):] for symbol in symbols}


def history(symbol: str, count: int) -> list[Bar]:
    day = date(2026, 10, 9)
    dates: list[date] = []
    while len(dates) < count:
        if day.weekday() < 5:
            dates.append(day)
        day -= timedelta(days=1)
    return [Bar(symbol, day.isoformat(), 100, 101, 99, 100, 1000) for day in reversed(dates)]


def test_learning_collects_320_bars_when_provider_caps_each_page_at_100() -> None:
    rows = history('AAPL', 400)
    provider = PagedHistory({'AAPL': rows})
    result = collect_completed_learning_bars(
        AppConfig(symbols=['AAPL'], bar_limit=320), provider,
        datetime(2026, 10, 10, tzinfo=UTC),
    )
    assert len(result['AAPL']) == 320
    assert result['AAPL'][0].timestamp == rows[-320].timestamp
    assert result['AAPL'][-1].timestamp == '2026-10-09'
    assert len(provider.calls) == 4


def test_provider_with_full_history_needs_only_initial_batch() -> None:
    rows = history('AAPL', 400)
    provider = PagedHistory({'AAPL': rows}, page_size=1000)
    result = collect_learning_history(provider, ['AAPL'], LearningHistoryWindow(
        '1Day', date(2024, 10, 9), date(2026, 10, 9), 320,
    ))
    assert result['AAPL'] == rows[-320:]
    assert len(provider.calls) == 1


def test_short_history_ends_at_empty_response_without_inventing_bars() -> None:
    rows = history('NEW', 73)
    provider = PagedHistory({'NEW': rows})
    result = collect_learning_history(provider, ['NEW', 'MISSING'], LearningHistoryWindow(
        '1Day', date(2024, 10, 9), date(2026, 10, 9), 320,
    ))
    assert result == {'NEW': rows, 'MISSING': []}
    assert len(provider.calls) == 2
    assert provider.calls[-1][2] == (date.fromisoformat(rows[0].timestamp) - timedelta(days=1)).isoformat()


def test_requested_dates_filter_provider_ignoring_start_and_preserve_gaps() -> None:
    rows = [row for row in history('AAPL', 50) if row.timestamp != '2026-10-07']
    provider = StaticPage({'AAPL': rows})
    result = collect_learning_history(provider, ['AAPL'], LearningHistoryWindow(
        '1Day', date(2026, 10, 1), date(2026, 10, 8), 320,
    ))
    assert [row.timestamp for row in result['AAPL']] == [
        '2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06', '2026-10-08',
    ]
    assert len(provider.calls) == 1


class StaticPage(PagedHistory):
    @override
    def get_stock_bars(self, symbols: list[str], timeframe: str, start: str,
                       end: str | None = None, limit: int = 1000) -> dict[str, list[Bar]]:
        self.calls.append((symbols, start, end, limit))
        return self.histories


def test_stale_page_fails_instead_of_looping_or_faking_306_bars() -> None:
    provider = StaticPage({'AAPL': history('AAPL', 100)})
    with pytest.raises(LearningHistoryError, match='cursor_not_advancing'):
        _ = collect_learning_history(provider, ['AAPL'], LearningHistoryWindow(
            '1Day', date(2024, 10, 9), date(2026, 10, 9), 320,
        ))
    assert len(provider.calls) == 2


def test_unsorted_identical_duplicates_are_sorted_and_deduplicated() -> None:
    rows = history('AAPL', 3)
    provider = StaticPage({'AAPL': [rows[2], rows[1], rows[1], rows[0]]})
    result = collect_learning_history(provider, ['AAPL'], LearningHistoryWindow(
        '1Day', date(2026, 10, 7), date(2026, 10, 9), 320,
    ))
    assert result['AAPL'] == rows


def test_conflicting_duplicate_prices_and_invalid_dates_fail_closed() -> None:
    rows = history('AAPL', 3)
    for invalid, reason in ((replace(rows[0], close=101), 'duplicate_conflict'),
                            (replace(rows[0], timestamp='invalid'), 'timestamp_invalid')):
        provider = StaticPage({'AAPL': [*rows, invalid]})
        with pytest.raises(LearningHistoryError, match=reason):
            _ = collect_learning_history(provider, ['AAPL'], LearningHistoryWindow(
                '1Day', date(2026, 10, 7), date(2026, 10, 9), 320,
            ))


def test_bounded_pagination_fails_closed_before_unlimited_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(learning_history, 'MAX_HISTORY_PAGES', 2)
    provider = PagedHistory({'AAPL': history('AAPL', 400)}, page_size=100)
    with pytest.raises(learning_history.LearningHistoryError, match='page_limit'):
        _ = learning_history.collect_learning_history(provider, ['AAPL'], learning_history.LearningHistoryWindow(
            '1Day', date(2024, 10, 9), date(2026, 10, 9), 320,
        ))
    assert len(provider.calls) == 2
