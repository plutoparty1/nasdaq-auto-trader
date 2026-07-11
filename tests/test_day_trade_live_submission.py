import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.day_trade import (
    DayTradeTestConfig,
    DayTradeTestPlanner,
    OrderRecordStore,
    build_live_buy_confirmation_phrase,
)
from nasdaq_auto_trader.models import OrderRequest


class DayTradeLiveSubmissionTests(unittest.TestCase):
    def test_guarded_live_buy_blocks_rejected_broker_response(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            record_path = Path(temp_dir) / "orders.jsonl"
            planner = DayTradeTestPlanner(
                DayTradeTestConfig(record_path=record_path),
                OrderRecordStore(record_path),
            )
            client = _RejectedDayTradeClient()
            plan = planner.build_plan(
                client,
                ["GOOD"],
                dry_run=False,
                live_trading=True,
                now=datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
            )
            phrase = build_live_buy_confirmation_phrase(plan)

            result = planner.submit_live_buy_order(
                client,
                plan,
                dry_run=False,
                live_trading=True,
                confirm_input=lambda prompt: phrase,
                output=lambda line: None,
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "order_response_not_submitted:rejected")
        self.assertFalse(result["submitted_order"])
        self.assertEqual(len(client.submitted_orders), 1)
        self.assertFalse(plan["submitted_order"])
        self.assertFalse(plan["buy_order"]["submitted_order"])


class _RejectedDayTradeClient:
    def __init__(self) -> None:
        self.submitted_orders: list[OrderRequest] = []

    def get_price_detail(self, symbol: str) -> JsonObject:
        return {
            "name": "Good Test Corp",
            "last": "10.00",
            "base": "9.80",
            "high": "10.50",
            "low": "9.70",
            "tvol": "1000000",
        }

    def get_best_quote(self, symbol: str) -> JsonObject:
        return {"pbid1": "9.99", "pask1": "10.01", "vbid1": "1000", "vask1": "1100"}

    def get_overseas_buying_power(
        self,
        symbol: str,
        order_price: float | None = None,
    ) -> float:
        del symbol, order_price
        return 64.0

    def submit_order(self, order: OrderRequest) -> JsonObject:
        self.submitted_orders.append(order)
        return {"id": "broker-order-1", "status": "rejected"}


if __name__ == "__main__":
    unittest.main()
