import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.day_trade import (
    DayTradeTestConfig,
    DayTradeTestPlanner,
    OrderRecordStore,
    build_live_buy_confirmation_phrase,
)
from tests.day_trade_fixtures import FakeDayTradeClient


class DayTradeConfirmationTests(unittest.TestCase):
    def _build_plan(self, temp_dir: str):
        record_path = Path(temp_dir) / "orders.jsonl"
        store = OrderRecordStore(record_path)
        planner = DayTradeTestPlanner(DayTradeTestConfig(record_path=record_path), store)
        client = FakeDayTradeClient()
        plan = planner.build_plan(
            client,
            ["GOOD"],
            dry_run=False,
            live_trading=True,
            now=datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
        )
        return planner, client, plan, store

    def test_guarded_live_buy_cancels_when_confirmation_does_not_match(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            planner, client, plan, _ = self._build_plan(temp_dir)
            output_lines = []
            result = planner.submit_live_buy_order(
                client,
                plan,
                dry_run=False,
                live_trading=True,
                confirm_input=lambda prompt: "NO",
                output=output_lines.append,
            )

        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["reason"], "confirmation_format_mismatch")
        self.assertFalse(result["submitted_order"])
        self.assertEqual(client.submitted_orders, [])
        rendered = "\n".join(output_lines)
        self.assertIn("Good Test Corp", rendered)
        self.assertIn("GOOD", rendered)
        self.assertIn("10.0100 USD", rendered)
        self.assertIn("Accepted price tolerance: 1.00%", rendered)

    def test_guarded_live_buy_submits_only_after_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            planner, client, plan, store = self._build_plan(temp_dir)
            phrase = build_live_buy_confirmation_phrase(plan)
            result = planner.submit_live_buy_order(
                client,
                plan,
                dry_run=False,
                live_trading=True,
                confirm_input=lambda prompt: phrase,
                output=lambda line: None,
            )
            live_buy_today = store.has_live_buy_today("2026-06-26")

        self.assertEqual(phrase, "BUY GOOD 1 @ 10.0100")
        self.assertEqual(result["status"], "submitted")
        self.assertTrue(result["submitted_order"])
        self.assertEqual(result["confirmation"]["accepted_by"], "exact_match")
        self.assertTrue(live_buy_today)
        self.assertEqual(len(client.submitted_orders), 1)
        submitted = client.submitted_orders[0]
        self.assertEqual(submitted.symbol, "GOOD")
        self.assertEqual(submitted.side, "buy")
        self.assertEqual(submitted.type, "limit")
        self.assertEqual(submitted.qty, 1.0)
        self.assertEqual(submitted.limit_price, 10.01)
        self.assertEqual(client.account_calls, [True])

    def test_guarded_live_buy_blocks_when_refreshed_cash_is_insufficient(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            planner, client, plan, _ = self._build_plan(temp_dir)
            phrase = build_live_buy_confirmation_phrase(plan)
            plan["buy_order"]["estimated_required_amount"] = 1.0
            client.cash = 5.0
            result = planner.submit_live_buy_order(
                client,
                plan,
                dry_run=False,
                live_trading=True,
                confirm_input=lambda prompt: phrase,
                output=lambda line: None,
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "deposited_cash_insufficient")
        self.assertFalse(result["submitted_order"])
        self.assertEqual(client.submitted_orders, [])
        self.assertEqual(client.account_calls, [True])

    def test_guarded_live_buy_accepts_stale_price_inside_tolerance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            planner, client, plan, _ = self._build_plan(temp_dir)
            result = planner.submit_live_buy_order(
                client,
                plan,
                dry_run=False,
                live_trading=True,
                confirm_input=lambda prompt: "BUY GOOD 1 @ 10.0800",
                output=lambda line: None,
            )

        self.assertEqual(result["status"], "submitted")
        self.assertTrue(result["submitted_order"])
        self.assertEqual(result["confirmation"]["accepted_by"], "price_tolerance")
        self.assertLess(result["confirmation"]["price_diff_pct"], 1.0)
        self.assertEqual(client.submitted_orders[0].limit_price, 10.01)

    def test_guarded_live_buy_rejects_stale_price_outside_tolerance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            planner, client, plan, _ = self._build_plan(temp_dir)
            result = planner.submit_live_buy_order(
                client,
                plan,
                dry_run=False,
                live_trading=True,
                confirm_input=lambda prompt: "BUY GOOD 1 @ 10.3000",
                output=lambda line: None,
            )

        self.assertEqual(result["status"], "cancelled")
        self.assertFalse(result["submitted_order"])
        self.assertEqual(result["reason"], "confirmation_price_outside_tolerance")
        self.assertEqual(client.submitted_orders, [])


if __name__ == "__main__":
    unittest.main()
