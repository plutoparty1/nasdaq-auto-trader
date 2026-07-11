import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.models import AccountSnapshot, Position
from nasdaq_auto_trader.sell_monitor import (
    HiveSellMonitor,
    HiveSellMonitorConfig,
    SellMonitorLog,
)


class FakeSellClient:
    def __init__(
        self,
        qty=1,
        avg_entry_price=100.0,
        last=102.0,
        bid=101.9,
        ask=102.0,
        fill_on_submit=True,
    ):
        self.qty = qty
        self.avg_entry_price = avg_entry_price
        self.last = last
        self.bid = bid
        self.ask = ask
        self.fill_on_submit = fill_on_submit
        self.orders = []

    def get_account(self, refresh=False):
        return AccountSnapshot(cash=0, equity=self.last * self.qty, buying_power=0)

    def list_positions(self, refresh=False):
        if self.qty <= 0:
            return {}
        return {
            "HIVE": Position(
                symbol="HIVE",
                qty=self.qty,
                market_value=self.last * self.qty,
                avg_entry_price=self.avg_entry_price,
            )
        }

    def get_price_detail(self, symbol):
        return {"last": str(self.last)}

    def get_best_quote(self, symbol):
        return {"pbid1": str(self.bid), "pask1": str(self.ask)}

    def submit_order(self, order):
        self.orders.append(order)
        if self.fill_on_submit:
            self.qty = 0
        return {"rt_cd": "0", "output": {"ODNO": "test-order"}}


def open_clock():
    return datetime(2026, 6, 26, 15, 0, tzinfo=timezone.utc)


def near_close_clock():
    return datetime(2026, 6, 26, 19, 55, tzinfo=timezone.utc)


class HiveSellMonitorTests(unittest.TestCase):
    def test_take_profit_submits_hive_sell_only_and_confirms_sold(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = FakeSellClient(avg_entry_price=100, last=102, bid=101.9)
            monitor = HiveSellMonitor(
                client,
                HiveSellMonitorConfig(
                    record_path=Path(temp_dir) / "sell.jsonl",
                    fill_check_seconds=0.01,
                    fill_poll_seconds=0,
                    poll_seconds=0,
                ),
                log=SellMonitorLog(Path(temp_dir) / "sell.jsonl"),
                clock=open_clock,
                sleeper=lambda seconds: None,
                output=lambda line: None,
            )

            result = monitor.run()

        self.assertEqual(result["status"], "sold")
        self.assertEqual(result["trigger"], "take_profit")
        self.assertEqual(len(client.orders), 1)
        self.assertEqual(client.orders[0].symbol, "HIVE")
        self.assertEqual(client.orders[0].side, "sell")
        self.assertEqual(client.orders[0].qty, 1)

    def test_loss_state_holds_without_stop_loss_order_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = FakeSellClient(avg_entry_price=100, last=98.5, bid=98.4)
            output = []
            monitor = HiveSellMonitor(
                client,
                HiveSellMonitorConfig(
                    record_path=Path(temp_dir) / "sell.jsonl",
                    fill_check_seconds=0.01,
                    fill_poll_seconds=0,
                    poll_seconds=0,
                ),
                log=SellMonitorLog(Path(temp_dir) / "sell.jsonl"),
                clock=open_clock,
                sleeper=lambda seconds: None,
                output=output.append,
            )

            result = monitor.run(max_loops=1)
            log_text = (Path(temp_dir) / "sell.jsonl").read_text(encoding="utf-8")

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["reason"], "max_loops_reached")
        self.assertEqual(client.orders, [])
        self.assertIn("HOLD: 손실 상태이므로 매도하지 않음", output)
        self.assertIn("hold_unprofitable", log_text)

    def test_force_sell_before_close_is_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = FakeSellClient(avg_entry_price=100, last=100.5, bid=100.4)
            monitor = HiveSellMonitor(
                client,
                HiveSellMonitorConfig(
                    record_path=Path(temp_dir) / "sell.jsonl",
                    poll_seconds=0,
                ),
                log=SellMonitorLog(Path(temp_dir) / "sell.jsonl"),
                clock=near_close_clock,
                sleeper=lambda seconds: None,
                output=lambda line: None,
            )

            result = monitor.run(max_loops=1)

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["reason"], "max_loops_reached")
        self.assertEqual(client.orders, [])

    def test_unexpected_qty_blocks_without_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = FakeSellClient(qty=2, avg_entry_price=100, last=102)
            monitor = HiveSellMonitor(
                client,
                HiveSellMonitorConfig(record_path=Path(temp_dir) / "sell.jsonl"),
                log=SellMonitorLog(Path(temp_dir) / "sell.jsonl"),
                clock=open_clock,
                sleeper=lambda seconds: None,
                output=lambda line: None,
            )

            result = monitor.run(max_loops=1)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "unexpected_hive_position_qty")
        self.assertEqual(client.orders, [])

    def test_existing_sell_record_prevents_duplicate_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "sell.jsonl"
            log = SellMonitorLog(log_path)
            log.append(
                {
                    "market_date": "2026-06-26",
                    "symbol": "HIVE",
                    "side": "sell",
                    "submitted_order": True,
                }
            )
            client = FakeSellClient(
                avg_entry_price=100,
                last=102,
                bid=101.9,
                fill_on_submit=False,
            )
            monitor = HiveSellMonitor(
                client,
                HiveSellMonitorConfig(record_path=log_path, poll_seconds=0),
                log=log,
                clock=open_clock,
                sleeper=lambda seconds: None,
                output=lambda line: None,
            )

            result = monitor.run(max_loops=1)

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["reason"], "max_loops_reached")
        self.assertEqual(client.orders, [])

    def test_dry_run_never_submits_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = FakeSellClient(avg_entry_price=100, last=102, bid=101.9)
            monitor = HiveSellMonitor(
                client,
                HiveSellMonitorConfig(
                    dry_run=True,
                    record_path=Path(temp_dir) / "sell.jsonl",
                    poll_seconds=0,
                ),
                log=SellMonitorLog(Path(temp_dir) / "sell.jsonl"),
                clock=open_clock,
                sleeper=lambda seconds: None,
                output=lambda line: None,
            )

            result = monitor.run(max_loops=1)

        self.assertEqual(result["status"], "dry_run_submitted")
        self.assertEqual(result["submitted_order"], False)
        self.assertEqual(client.orders, [])


if __name__ == "__main__":
    unittest.main()
