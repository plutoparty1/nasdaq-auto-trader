import tempfile
import unittest
from datetime import datetime, timezone
from http.client import RemoteDisconnected
from pathlib import Path
from unittest.mock import patch

from nasdaq_auto_trader.broker import (
    AlpacaCredentials,
    BrokerRequestError,
    KISClient,
    KISCredentials,
)
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest, Position
from nasdaq_auto_trader.risk import RiskConfig
from nasdaq_auto_trader.sell_monitor import (
    HiveSellMonitor,
    HiveSellMonitorConfig,
    SellMonitorLog,
)
from tests.ai_decision_fixtures import MultiSymbolMarketData, compact_strategy


class KISOrderRetrySafetyTests(unittest.TestCase):
    def test_remote_disconnect_retries_read_only_get_once(self):
        client = _DisconnectedReadClient()

        with patch("nasdaq_auto_trader.brokers.kis_auth.time.sleep"):
            result = client._request("GET", "/read-only", "READ001")

        self.assertEqual(result, {"rt_cd": "0"})
        self.assertEqual(client.open_count, 2)

    def test_remote_disconnect_does_not_retry_post(self):
        client = _DisconnectedReadClient(always_disconnect=True)

        with self.assertRaises(RemoteDisconnected):
            client._request("POST", "/order", "ORDER001", body={"qty": 1})

        self.assertEqual(client.open_count, 1)

    def test_post_disconnect_remains_single_attempt_in_unattended_mode(self):
        client = _DisconnectedReadClient(always_disconnect=True)

        with self.assertRaises(RemoteDisconnected):
            client._request("POST", "/order", "ORDER001", body={"qty": 1})

        self.assertEqual(client.open_count, 1)

    def test_rate_limit_response_does_not_retry_order_post(self):
        client = _RateLimitedOrderClient()

        with self.assertRaises(BrokerRequestError):
            client.submit_order(
                OrderRequest(
                    symbol="QQQ",
                    side="buy",
                    type="limit",
                    qty=1,
                    limit_price=500,
                )
            )

        self.assertEqual(client.open_count, 1)

    def test_sell_monitor_does_not_retry_ambiguous_submission_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = _AmbiguousSellClient()
            monitor = HiveSellMonitor(
                client,
                HiveSellMonitorConfig(
                    max_retries=3,
                    record_path=Path(temp_dir) / "sell.jsonl",
                    poll_seconds=0,
                ),
                log=SellMonitorLog(Path(temp_dir) / "sell.jsonl"),
                clock=lambda: datetime(2026, 6, 26, 15, 0, tzinfo=timezone.utc),
                sleeper=lambda seconds: None,
                output=lambda line: None,
            )

            result = monitor.run(max_loops=1)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "order_submission_outcome_unknown")
        self.assertEqual(client.submit_count, 1)

    def test_ambiguous_engine_response_is_terminal_and_stops_the_cycle(self):
        for broker_response in ({}, {"unexpected": "payload"}):
            with self.subTest(broker_response=broker_response):
                broker = _AmbiguousEngineBroker(broker_response)
                engine = TradingEngine(
                    AppConfig(
                        mode="paper",
                        regular_market_hours_only=False,
                        symbols=["QQQ", "AAPL"],
                        alpaca=AlpacaCredentials("key", "secret"),
                        strategy=compact_strategy(),
                        risk=RiskConfig(max_position_pct=0.2, risk_per_trade_pct=0),
                    ),
                    broker=broker,
                    market_data=MultiSymbolMarketData(),
                    account=AccountSnapshot(
                        cash=10_000,
                        equity=10_000,
                        buying_power=10_000,
                    ),
                    positions={},
                )

                results = engine.run_once()

                self.assertEqual(len(results), 1)
                self.assertEqual(broker.submit_count, 1)
                response = results[0]["response"]
                self.assertEqual(response["status"], "blocked")
                self.assertEqual(response["reason"], "order_response_reconcile_required")
                self.assertTrue(response["terminal"])
                self.assertEqual(response["broker_response"], broker_response)


class _RateLimitedOrderClient(KISClient):
    def __init__(self) -> None:
        super().__init__(KISCredentials("app", "secret", "12345678", paper=True))
        self.open_count = 0

    def _ensure_token(self) -> None:
        self._access_token = "test-token"

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        del refresh
        return AccountSnapshot(cash=500, equity=500, buying_power=500)

    def get_overseas_buying_power(
        self,
        symbol: str,
        order_price: float | None = None,
    ) -> float:
        del symbol, order_price
        return 500.0

    def _open_json(self, request, label):
        del request, label
        self.open_count += 1
        raise BrokerRequestError("KIS API error: EGW00201")


class _DisconnectedReadClient(KISClient):
    def __init__(self, always_disconnect: bool = False) -> None:
        super().__init__(KISCredentials("app", "secret", "12345678", paper=True))
        self.open_count = 0
        self.always_disconnect = always_disconnect

    def _ensure_token(self) -> None:
        self._access_token = "test-token"

    def _open_json(self, request, label):
        del request, label
        self.open_count += 1
        if self.always_disconnect or self.open_count == 1:
            raise RemoteDisconnected("remote closed connection")
        return {"rt_cd": "0"}


class _AmbiguousSellClient:
    def __init__(self) -> None:
        self.submit_count = 0

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        del refresh
        return AccountSnapshot(cash=0, equity=102, buying_power=0)

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        del refresh
        return {
            "HIVE": Position("HIVE", 1, 102, 100),
        }

    def get_price_detail(self, symbol: str) -> dict[str, str]:
        del symbol
        return {"last": "102"}

    def get_best_quote(self, symbol: str) -> dict[str, str]:
        del symbol
        return {"pbid1": "101.9", "pask1": "102"}

    def submit_order(self, order: OrderRequest) -> dict[str, str]:
        del order
        self.submit_count += 1
        raise BrokerRequestError("response lost after submission")


class _AmbiguousEngineBroker:
    def __init__(self, response: dict[str, str]) -> None:
        self.response = response
        self.submit_count = 0

    def submit_order(self, order: OrderRequest) -> dict[str, str]:
        del order
        self.submit_count += 1
        return self.response


if __name__ == "__main__":
    unittest.main()
