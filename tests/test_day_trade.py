import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.day_trade import (
    DayTradeTestConfig,
    DayTradeTestPlanner,
    LiveOrderSafetyError,
    OrderRecordStore,
    assert_live_order_allowed,
    build_live_buy_confirmation_phrase,
)
from tests.day_trade_fixtures import FakeDayTradeClient


class DayTradePlannerTests(unittest.TestCase):
    def test_build_plan_selects_one_affordable_candidate_and_records_dry_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            record_path = Path(temp_dir) / "orders.jsonl"
            planner = DayTradeTestPlanner(
                DayTradeTestConfig(record_path=record_path),
                OrderRecordStore(record_path),
            )

            plan = planner.build_plan(
                FakeDayTradeClient(),
                ["WIDE", "LOWVOL", "EXPENSIVE", "GOOD"],
                now=datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
            )

            records = [
                json.loads(line)
                for line in record_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(plan["status"], "planned")
        self.assertTrue(plan["dry_run"])
        self.assertFalse(plan["live_trading"])
        self.assertFalse(plan["submitted_order"])
        self.assertEqual(plan["buy_order"]["symbol"], "GOOD")
        self.assertEqual(plan["selected"]["name"], "Good Test Corp")
        self.assertEqual(plan["buy_order"]["qty"], 1)
        self.assertEqual(plan["buy_order"]["order_type"], "limit")
        self.assertEqual(plan["sell_plan"]["take_profit_limit_price"], 10.1601)
        self.assertEqual(plan["sell_plan"]["stop_loss_trigger_price"], 9.9099)
        self.assertEqual(records[0]["action"], "buy")
        self.assertFalse(records[0]["submitted_order"])

        by_symbol = {item["symbol"]: item for item in plan["candidates"]}
        self.assertIn("spread_too_wide", by_symbol["WIDE"]["exclude_reasons"])
        self.assertIn("volume_too_low", by_symbol["LOWVOL"]["exclude_reasons"])
        self.assertIn(
            "price_above_max_total_usd",
            by_symbol["EXPENSIVE"]["exclude_reasons"],
        )

    def test_plan_blocks_when_buying_power_is_insufficient(self):
        class LowBuyingPowerClient(FakeDayTradeClient):
            def get_overseas_buying_power(self, symbol, order_price=None):
                return 5.0

        with tempfile.TemporaryDirectory() as temp_dir:
            planner = DayTradeTestPlanner(
                DayTradeTestConfig(record_path=Path(temp_dir) / "orders.jsonl")
            )

            plan = planner.build_plan(
                LowBuyingPowerClient(),
                ["GOOD"],
                now=datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(plan["status"], "blocked")
        self.assertIn("no_candidate_passed_filters_and_buying_power", plan["blockers"])
        self.assertIn("buying_power_insufficient", plan["candidates"][0]["exclude_reasons"])

    def test_record_store_counts_only_live_submitted_buys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = OrderRecordStore(Path(temp_dir) / "orders.jsonl")
            store.append(
                {
                    "market_date": "2026-06-26",
                    "action": "buy",
                    "submitted_order": False,
                    "dry_run": True,
                    "live_trading": False,
                }
            )
            self.assertFalse(store.has_live_buy_today("2026-06-26"))
            store.append(
                {
                    "market_date": "2026-06-26",
                    "action": "buy",
                    "submitted_order": True,
                    "dry_run": False,
                    "live_trading": True,
                }
            )

            self.assertTrue(store.has_live_buy_today("2026-06-26"))

    def test_live_order_guard_blocks_dry_run_and_non_live_mode(self):
        with self.assertRaises(RuntimeError):
            assert_live_order_allowed(dry_run=True, live_trading=True)
        with self.assertRaises(RuntimeError):
            assert_live_order_allowed(dry_run=False, live_trading=False)
        assert_live_order_allowed(dry_run=False, live_trading=True)

    def test_guarded_live_buy_cancels_when_confirmation_does_not_match(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            record_path = Path(temp_dir) / "orders.jsonl"
            planner = DayTradeTestPlanner(
                DayTradeTestConfig(record_path=record_path),
                OrderRecordStore(record_path),
            )
            client = FakeDayTradeClient()
            plan = planner.build_plan(
                client,
                ["GOOD"],
                dry_run=False,
                live_trading=True,
                now=datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
            )
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
        self.assertIn("Good Test Corp", "\n".join(output_lines))
        self.assertIn("GOOD", "\n".join(output_lines))
        self.assertIn("10.0100 USD", "\n".join(output_lines))
        self.assertIn("Accepted price tolerance: 1.00%", "\n".join(output_lines))

    def test_guarded_live_buy_submits_only_after_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            record_path = Path(temp_dir) / "orders.jsonl"
            store = OrderRecordStore(record_path)
            planner = DayTradeTestPlanner(
                DayTradeTestConfig(record_path=record_path),
                store,
            )
            client = FakeDayTradeClient()
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

    def test_guarded_live_buy_accepts_stale_price_inside_tolerance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            record_path = Path(temp_dir) / "orders.jsonl"
            planner = DayTradeTestPlanner(
                DayTradeTestConfig(
                    confirmation_price_tolerance_pct=1.0,
                    record_path=record_path,
                ),
                OrderRecordStore(record_path),
            )
            client = FakeDayTradeClient()
            plan = planner.build_plan(
                client,
                ["GOOD"],
                dry_run=False,
                live_trading=True,
                now=datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
            )

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
            record_path = Path(temp_dir) / "orders.jsonl"
            planner = DayTradeTestPlanner(
                DayTradeTestConfig(
                    confirmation_price_tolerance_pct=1.0,
                    record_path=record_path,
                ),
                OrderRecordStore(record_path),
            )
            client = FakeDayTradeClient()
            plan = planner.build_plan(
                client,
                ["GOOD"],
                dry_run=False,
                live_trading=True,
                now=datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
            )

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
