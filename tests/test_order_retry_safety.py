import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.broker import (
    BrokerRequestError,
    KISClient,
    KISCredentials,
)
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest, Position
from nasdaq_auto_trader.sell_monitor import (
    HiveSellMonitor,
    HiveSellMonitorConfig,
    SellMonitorLog,
)


class KISOrderRetrySafetyTests(unittest.TestCase):
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


class _RateLimitedOrderClient(KISClient):
    def __init__(self) -> None:
        super().__init__(KISCredentials("app", "secret", "12345678", paper=True))
        self.open_count = 0

    def _ensure_token(self) -> None:
        self._access_token = "test-token"

    def _open_json(self, request, label):
        del request, label
        self.open_count += 1
        raise BrokerRequestError("KIS API error: EGW00201")


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


if __name__ == "__main__":
    unittest.main()
