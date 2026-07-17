import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.intraday_shadow_scan import run_intraday_shadow_scan
from nasdaq_auto_trader.models import Bar


class FakeShadowMarketData:
    def __init__(self):
        self.liquidity_limit = None
        self.order_calls = 0
        self.requested_end = None

    def get_liquid_overseas_symbols(self, universe, limit=30):
        self.liquidity_limit = limit
        return ("AAPL", "MSFT")

    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        del timeframe, start, limit
        self.requested_end = end
        base = datetime(2026, 5, 28, tzinfo=timezone.utc)
        return {
            symbol: [
                Bar(
                    symbol=symbol,
                    timestamp=(base + timedelta(days=index)).isoformat(),
                    open=100 + index,
                    high=102 + index,
                    low=99 + index,
                    close=101 + index,
                    volume=1_000_000,
                )
                for index in range(30)
            ]
            for symbol in symbols
        }

    def get_best_quote(self, symbol):
        del symbol
        return {"pbid1": "129.9", "pask1": "130.1"}

    def submit_order(self, order):
        del order
        self.order_calls += 1
        raise AssertionError("shadow scan must never submit an order")


class IntradayShadowScanTests(unittest.TestCase):
    def test_kis_scan_is_bounded_persisted_and_orderless(self):
        market_data = FakeShadowMarketData()
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_intraday_shadow_scan(
                AppConfig(mode="live", broker="kis"),
                market_data,
                datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
                Path(temp_dir) / "scan.json",
            )

            report_file_exists = report.report_path.exists()

        self.assertEqual(market_data.liquidity_limit, 30)
        self.assertEqual(report.scanned_symbols, ("AAPL", "MSFT"))
        self.assertEqual(report.eligible_symbols, ("AAPL", "MSFT"))
        self.assertFalse(report.submitted_order)
        self.assertEqual(market_data.order_calls, 0)
        self.assertEqual(market_data.requested_end, "2026-06-25")
        self.assertTrue(report_file_exists)
