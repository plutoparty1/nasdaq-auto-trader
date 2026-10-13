import unittest
from datetime import datetime, timezone

from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.learning_data import collect_completed_learning_bars
from nasdaq_auto_trader.models import Bar


class RecordingMarketData:
    def __init__(self):
        self.calls = []

    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        self.calls.append((symbols, timeframe, start, end, limit))
        if end is not None and end < "2026-06-25":
            return {symbol: [] for symbol in symbols}
        return {symbol: [Bar(symbol, "2026-06-25T20:00:00+00:00", 100, 101, 99, 100, 1000)] for symbol in symbols}


class LearningDataTests(unittest.TestCase):
    def test_collection_excludes_current_open_session(self):
        provider = RecordingMarketData()

        result = collect_completed_learning_bars(
            AppConfig(symbols=["QQQ", "AAPL"]),
            provider,
            datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(provider.calls[0][3], "2026-06-25")
        self.assertEqual(sorted(result), ["AAPL", "QQQ"])
        self.assertEqual(result["QQQ"][0].timestamp, "2026-06-25T20:00:00+00:00")
