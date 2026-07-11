import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.brokers.alpaca import AlpacaClient, AlpacaCredentials
from nasdaq_auto_trader.brokers.kis_client import KISClient, KISCredentials
from nasdaq_auto_trader.quant_data.market_quality import filter_tradeable_symbols
from nasdaq_auto_trader.quant_data.selection_cache import (
    SelectionCache,
    SelectionCacheIdentity,
)
from nasdaq_auto_trader.quant_data.symbol_selector import RankedSymbol, SelectionReport
from nasdaq_auto_trader.dry_run_market_data import DryRunMarketData
from tests.ai_quant_fixtures import bars


class AutoSymbolMarketTests(unittest.TestCase):
    def test_offline_dry_run_bars_use_fresh_iso_timestamps(self):
        market = DryRunMarketData()
        loaded = market.get_stock_bars(
            ["AAPL"],
            "1Day",
            "2026-01-01",
            "2026-07-10",
            80,
        )
        price_bars = [
            type(bars("AAPL")[0])(
                item.symbol,
                item.timestamp,
                item.open,
                item.high,
                item.low,
                item.close,
                item.volume,
                bid=99.99,
                ask=100.01,
            )
            for item in loaded["AAPL"]
        ]

        result = filter_tradeable_symbols(
            {"AAPL": price_bars},
            now=datetime(2026, 7, 11, tzinfo=timezone.utc),
            quotes_required=True,
        )

        self.assertEqual(result.symbols, ("AAPL",))
    def test_kis_liquidity_intersection_preserves_rank_and_limit(self):
        client = _RankingKISClient(
            KISCredentials("app", "secret", "account", paper=False),
            ["TSLA", "AAPL", "OTHER", "MSFT"],
        )

        symbols = client.get_liquid_overseas_symbols(
            {"AAPL", "MSFT", "TSLA"},
            limit=2,
        )

        self.assertEqual(symbols, ("TSLA", "AAPL"))
        self.assertEqual(client.calls, 1)

    def test_kis_exchange_identity_mismatch_blocks_before_request(self):
        client = _RankingKISClient(
            KISCredentials(
                "app",
                "secret",
                "account",
                paper=False,
                order_exchange_code="NYSE",
                price_exchange_code="NAS",
            ),
            ["AAPL"],
        )

        with self.assertRaises(BrokerRequestError) as raised:
            client.get_liquid_overseas_symbols({"AAPL"}, limit=30)

        self.assertIn("kis_exchange_identity_mismatch", str(raised.exception))
        self.assertEqual(client.calls, 0)

    def test_kis_duplicate_or_malformed_rank_payload_fails_whole_shortlist(self):
        for rows in (
            [{"symb": "AAPL"}, {"symb": "AAPL"}],
            [{"name": "missing symbol"}],
            "invalid",
        ):
            with self.subTest(rows=rows):
                client = _PayloadKISClient(rows)
                with self.assertRaises(BrokerRequestError):
                    client.get_liquid_overseas_symbols({"AAPL"}, limit=30)

    def test_market_quality_rejects_bad_price_volume_spread_and_history(self):
        good = bars("AAPL")
        bad_price = [*bars("MSFT")]
        bad_price[-1] = _replace_bar(bad_price[-1], close=0)
        bad_spread = [*bars("TSLA")]
        bad_spread[-1] = _replace_bar(bad_spread[-1], bid=90, ask=110)
        no_volume = [_replace_bar(item, volume=0) for item in bars("NVDA")]

        result = filter_tradeable_symbols(
            {
                "AAPL": good,
                "MSFT": bad_price,
                "TSLA": bad_spread,
                "NVDA": no_volume,
                "SHORT": bars("SHORT")[:5],
            }
        )

        self.assertEqual(result.symbols, ("AAPL",))
        self.assertEqual(set(result.rejected), {"MSFT", "TSLA", "NVDA", "SHORT"})

    def test_market_quality_rejects_stale_low_value_missing_quote_and_outlier(self):
        now = datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)
        good = [_replace_bar(item, timestamp="2026-07-13T14:29:00+00:00") for item in bars("AAPL")]
        stale = [_replace_bar(item, timestamp="2000-01-03T14:30:00+00:00") for item in bars("MSFT")]
        low_value = [_replace_bar(item, timestamp="2026-07-13T14:29:00+00:00", volume=1) for item in bars("NVDA")]
        missing_quote = [_replace_bar(item, timestamp="2026-07-13T14:29:00+00:00", bid=0, ask=0) for item in bars("TSLA")]
        outlier = [_replace_bar(item, timestamp="2026-07-13T14:29:00+00:00") for item in bars("AMZN")]
        outlier[-1] = _replace_bar(outlier[-1], close=outlier[-2].close * 1.5)

        result = filter_tradeable_symbols(
            {
                "AAPL": good,
                "MSFT": stale,
                "NVDA": low_value,
                "TSLA": missing_quote,
                "AMZN": outlier,
            },
            now=now,
            quotes_required=True,
        )

        self.assertEqual(result.symbols, ("AAPL",))
        self.assertIn("stale_market_data", result.rejected["MSFT"])
        self.assertIn("insufficient_dollar_volume", result.rejected["NVDA"])
        self.assertIn("quote_unavailable", result.rejected["TSLA"])
        self.assertIn("price_outlier", result.rejected["AMZN"])

    def test_cache_is_nonlive_identity_bound_and_corruption_safe(self):
        identity = SelectionCacheIdentity(
            provider="kis",
            mode="paper",
            universe_id="nasdaq_100",
            universe_version="sha256:test",
            universe_effective_date="2026-07-10",
            strategy_id="alpha",
            strategy_version="v1",
            strategy_digest="digest",
            registry_digest="registry",
            promoted_digest="promoted",
            market_date="2026-07-11",
            shortlist_limit=30,
        )
        report = SelectionReport(
            status="selected",
            universe_id="nasdaq_100",
            universe_effective_date="2026-07-10",
            strategy_id="alpha",
            strategy_version="v1",
            strategy_digest="digest",
            shortlist_count=1,
            ranked=(RankedSymbol("AAPL", 1.0, 0.9, ("momentum",)),),
            selected_symbols=("AAPL",),
            universe_version="sha256:test",
        )
        now = datetime(2026, 7, 11, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "latest.json"
            cache = SelectionCache(path, ttl=timedelta(minutes=15))
            cache.write(identity, report, now)

            loaded = cache.read(identity, now + timedelta(minutes=10))
            live = cache.read(identity, now, mode="live")
            path.write_text("{broken", encoding="utf-8")
            corrupt = cache.read(identity, now)

        self.assertEqual(loaded, report)
        self.assertIsNone(live)
        self.assertIsNone(corrupt)

    def test_alpaca_quotes_use_one_batch_and_reject_partial_payload(self):
        complete = _SnapshotAlpacaClient(
            {
                "AAPL": {"latestQuote": {"bp": 100, "ap": 101}},
                "MSFT": {"latestQuote": {"bp": 200, "ap": 201}},
            }
        )
        partial = _SnapshotAlpacaClient(
            {"AAPL": {"latestQuote": {"bp": 100, "ap": 101}}}
        )

        quotes = complete.get_latest_quotes(["AAPL", "MSFT"])
        with self.assertRaises(BrokerRequestError):
            partial.get_latest_quotes(["AAPL", "MSFT"])

        self.assertEqual(set(quotes), {"AAPL", "MSFT"})
        self.assertEqual(complete.calls, 1)


class _RankingKISClient(KISClient):
    def __init__(self, credentials: KISCredentials, symbols: list[str]) -> None:
        super().__init__(credentials)
        self.symbols = symbols
        self.calls = 0

    def _request(self, method, path, tr_id, params=None, body=None):
        self.calls += 1
        return {"output2": [{"symb": symbol} for symbol in self.symbols]}


class _PayloadKISClient(_RankingKISClient):
    def __init__(self, rows) -> None:
        super().__init__(KISCredentials("app", "secret", "account", paper=False), [])
        self.rows = rows

    def _request(self, method, path, tr_id, params=None, body=None):
        self.calls += 1
        return {"output2": self.rows}


class _SnapshotAlpacaClient(AlpacaClient):
    def __init__(self, payload) -> None:
        super().__init__(AlpacaCredentials("key", "secret"))
        self.payload = payload
        self.calls = 0

    def _request(self, method, base_url, path, params=None, body=None):
        self.calls += 1
        return self.payload


def _replace_bar(bar, **changes):
    values = {
        "symbol": bar.symbol,
        "timestamp": bar.timestamp,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "bid": bar.bid,
        "ask": bar.ask,
    }
    values.update(changes)
    return type(bar)(**values)


if __name__ == "__main__":
    unittest.main()
