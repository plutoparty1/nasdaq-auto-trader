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
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest


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

    def test_ambiguous_live_buy_requires_reconciliation_and_blocks_later_buys(self):
        for response in ({}, {"status": "unknown"}):
            with (
                self.subTest(response=response),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                record_path = Path(temp_dir) / "orders.jsonl"
                planner = DayTradeTestPlanner(
                    DayTradeTestConfig(record_path=record_path),
                    OrderRecordStore(record_path),
                )
                client = _AmbiguousDayTradeClient(response)
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
                later_plan = planner.build_plan(
                    client,
                    ["GOOD"],
                    dry_run=False,
                    live_trading=True,
                    now=datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
                )

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["reason"], "order_response_reconcile_required")
            self.assertTrue(result["terminal"])
            self.assertFalse(result["submitted_order"])
            self.assertEqual(result["response"], response)
            self.assertEqual(later_plan["status"], "blocked")
            self.assertIn("live_buy_already_recorded_today", later_plan["blockers"])
            self.assertEqual(len(client.submitted_orders), 1)


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

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        del refresh
        return AccountSnapshot(cash=64.0, equity=64.0, buying_power=64.0)

    def submit_order(self, order: OrderRequest) -> JsonObject:
        self.submitted_orders.append(order)
        return {"id": "broker-order-1", "status": "rejected"}


class _AmbiguousDayTradeClient(_RejectedDayTradeClient):
    def __init__(self, response: JsonObject) -> None:
        super().__init__()
        self.response = response

    def submit_order(self, order: OrderRequest) -> JsonObject:
        self.submitted_orders.append(order)
        return self.response


if __name__ == "__main__":
    unittest.main()
