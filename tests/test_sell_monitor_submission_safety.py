from datetime import datetime, timezone
from pathlib import Path

import pytest

from nasdaq_auto_trader.sell_monitor import HiveSellMonitor, HiveSellMonitorConfig, SellMonitorLog
from nasdaq_auto_trader.sell_monitor_types import SellMonitorSafetyError
from tests.test_sell_monitor import FakeSellClient, open_clock


class AmbiguousSellClient(FakeSellClient):
    def submit_order(self, order):
        self.orders.append(order)
        raise TimeoutError("synthetic response timeout after acceptance")


def test_sell_timeout_survives_restart_without_another_post(tmp_path: Path) -> None:
    client = AmbiguousSellClient(fill_on_submit=False)
    log = SellMonitorLog(tmp_path / "sell.jsonl")
    config = HiveSellMonitorConfig(record_path=log.path, poll_seconds=0)
    first = HiveSellMonitor(client, config, log, open_clock, lambda _: None, lambda _: None)
    assert first.run(max_loops=1)["reason"] == "order_submission_outcome_unknown"

    restarted = HiveSellMonitor(client, config, log, open_clock, lambda _: None, lambda _: None)
    result = restarted.run(max_loops=1)

    assert len(client.orders) == 1
    assert result["reason"] == "order_submission_outcome_unknown"


def test_sell_never_posts_after_market_closes_during_snapshot(tmp_path: Path) -> None:
    client = FakeSellClient(fill_on_submit=False)
    times = iter([
        datetime(2026, 6, 26, 19, 59, 59, tzinfo=timezone.utc),
        datetime(2026, 6, 26, 20, 0, 1, tzinfo=timezone.utc),
    ])
    config = HiveSellMonitorConfig(record_path=tmp_path / "sell.jsonl", fill_check_seconds=0)
    monitor = HiveSellMonitor(client, config, clock=lambda: next(times), output=lambda _: None)

    result = monitor.run(max_loops=1)

    assert client.orders == []
    assert result["reason"] == "market_not_open"


class PriceFallsBeforeSubmit(FakeSellClient):
    def __init__(self):
        super().__init__(fill_on_submit=False)
        self.price_reads = 0

    def get_price_detail(self, symbol):
        self.price_reads += 1
        if self.price_reads > 1:
            self.last = self.bid = self.ask = 98.0
        return super().get_price_detail(symbol)


def test_sell_rechecks_profit_trigger_with_fresh_quote(tmp_path: Path) -> None:
    client = PriceFallsBeforeSubmit()
    config = HiveSellMonitorConfig(record_path=tmp_path / "sell.jsonl", fill_check_seconds=0)
    monitor = HiveSellMonitor(client, config, clock=open_clock, output=lambda _: None)

    result = monitor.run(max_loops=1)

    assert client.orders == []
    assert result["reason"] == "sell_trigger_no_longer_active"


def test_dry_run_record_does_not_create_ambiguous_live_submission(tmp_path: Path) -> None:
    client = FakeSellClient(fill_on_submit=False)
    log = SellMonitorLog(tmp_path / "sell.jsonl")
    config = HiveSellMonitorConfig(record_path=log.path, dry_run=True)
    for _ in range(2):
        monitor = HiveSellMonitor(client, config, log, open_clock, output=lambda _: None)
        assert monitor.run(max_loops=1)["status"] == "dry_run_submitted"
    assert client.orders == []


def test_corrupt_sell_journal_blocks_before_post(tmp_path: Path) -> None:
    client = FakeSellClient()
    path = tmp_path / "sell.jsonl"
    path.write_text('{"event":"sell_order_attempt"', encoding="utf-8")
    config = HiveSellMonitorConfig(record_path=path)
    monitor = HiveSellMonitor(client, config, clock=open_clock, output=lambda _: None)
    with pytest.raises(SellMonitorSafetyError, match="reconciliation"):
        monitor.run(max_loops=1)
    assert client.orders == []


def test_profit_only_sell_never_posts_a_limit_below_entry(tmp_path: Path) -> None:
    client = FakeSellClient(last=102, bid=98, ask=102, fill_on_submit=False)
    config = HiveSellMonitorConfig(record_path=tmp_path / "sell.jsonl", fill_check_seconds=0)
    monitor = HiveSellMonitor(client, config, clock=open_clock, output=lambda _: None)

    result = monitor.run(max_loops=1)

    assert client.orders == []
    assert result["reason"] == "sell_limit_would_allow_loss"
