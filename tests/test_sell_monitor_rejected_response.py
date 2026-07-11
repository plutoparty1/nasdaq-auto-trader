import tempfile
import unittest
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest, Position
from nasdaq_auto_trader.sell_monitor import (
    HiveSellMonitor,
    HiveSellMonitorConfig,
    SellMonitorLog,
)


class HiveSellMonitorRejectedResponseTests(unittest.TestCase):
    def test_rejected_sell_response_blocks_without_pending_fill_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = _RejectedSellClient()
            monitor = HiveSellMonitor(
                client,
                HiveSellMonitorConfig(
                    max_retries=1,
                    record_path=Path(temp_dir) / "sell.jsonl",
                    fill_check_seconds=0.01,
                    fill_poll_seconds=0,
                    poll_seconds=0,
                ),
                log=SellMonitorLog(Path(temp_dir) / "sell.jsonl"),
                clock=lambda: datetime(2026, 6, 26, 15, 0, tzinfo=timezone.utc),
                sleeper=lambda seconds: None,
                output=lambda line: None,
            )

            result = monitor.run(max_loops=1)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "order_response_not_submitted:rejected")
        self.assertFalse(result["submitted_order"])
        self.assertEqual(len(client.orders), 1)


class _RejectedSellClient:
    def __init__(self) -> None:
        self.orders: list[OrderRequest] = []

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        del refresh
        return AccountSnapshot(cash=0, equity=102, buying_power=0)

    def list_positions(self, refresh: bool = False) -> Mapping[str, Position]:
        del refresh
        return {
            "HIVE": Position(
                symbol="HIVE",
                qty=1,
                market_value=102,
                avg_entry_price=100,
            )
        }

    def get_price_detail(self, symbol: str) -> JsonObject:
        del symbol
        return {"last": "102.0"}

    def get_best_quote(self, symbol: str) -> JsonObject:
        del symbol
        return {"pbid1": "101.9", "pask1": "102.0"}

    def submit_order(self, order: OrderRequest) -> JsonObject:
        self.orders.append(order)
        return {"id": "broker-order-1", "status": "rejected"}


if __name__ == "__main__":
    unittest.main()
