from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from nasdaq_auto_trader.brokers.kis_reconciliation import (
    KISOpenOrder,
    KISOrderHistory,
)
from nasdaq_auto_trader.live_canary_identity import account_fingerprint, executable_sha256
from nasdaq_auto_trader.live_canary_paths import CanaryPaths
from nasdaq_auto_trader.live_canary_policy import CANARY_POLICY, OrderSide
from nasdaq_auto_trader.live_canary_state import CanaryState, CanaryStateStore, OrderIntent, StateMode
from nasdaq_auto_trader.market_hours import MarketSession
from nasdaq_auto_trader.models import AccountSnapshot, Position
from tests.live_canary_runner_fixtures import (
    NOW,
    FakeKIS,
    armed_canary as _armed,
    run_canary as _run,
)


def test_missing_kis_order_id_persists_manual_state_and_stops_posts(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    broker = FakeKIS({}, submit_response={"output": {}})

    result = _run(config, paths, executable, broker)

    assert result.status.value == "manual_reconciliation_required"
    assert broker.posts == 1
    assert CanaryStateStore(paths.state).load(expected_nonce="nonce").mode is StateMode.MANUAL_RECONCILIATION_REQUIRED


def test_foreign_startup_position_rejects_before_any_post(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    broker = FakeKIS({"SPY": Position("SPY", 1.0, 19.0, 19.0)})

    result = _run(config, paths, executable, broker)

    assert result.status.value == "manual_reconciliation_required"
    assert broker.posts == 0


def test_post_startup_foreign_position_blocks_buy_before_post(tmp_path: Path) -> None:
    class ForeignPositionAfterCashRefreshKIS(FakeKIS):
        def __init__(self) -> None:
            super().__init__({})
            self.account_reads = 0

        def get_account(self, refresh: bool = False) -> AccountSnapshot:
            self.account_reads += 1
            if self.account_reads == 2:
                self.positions = {"SPY": Position("SPY", 1.0, 19.0, 19.0)}
            return super().get_account(refresh=refresh)

    paths, config, executable = _armed(tmp_path)
    broker = ForeignPositionAfterCashRefreshKIS()

    result = _run(config, paths, executable, broker)

    persisted = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    assert result.status.value == "manual_reconciliation_required"
    assert persisted.mode is StateMode.MANUAL_RECONCILIATION_REQUIRED
    assert broker.posts == 0


def test_exact_known_open_order_waits_until_cancel_timeout(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    state = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    CanaryStateStore(paths.state).save(
        state.record_intent(OrderIntent("QQQ", OrderSide.BUY, 1)).complete_intent(
            "buy-1", NOW
        )
    )
    open_order = KISOpenOrder("buy-1", "QQQ", "buy", 1.0, 0.0, 1.0, 19.5)
    broker = FakeKIS({}, (open_order,))

    _run(config, paths, executable, broker)

    assert broker.cancels == []
    assert broker.posts == 0


def test_exact_known_open_order_is_cancelled_after_timeout(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    state = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    submitted_at = NOW - timedelta(
        seconds=CANARY_POLICY.buy_order_timeout_seconds + 1
    )
    CanaryStateStore(paths.state).save(
        state.record_intent(OrderIntent("QQQ", OrderSide.BUY, 1)).complete_intent(
            "buy-1", submitted_at
        )
    )
    open_order = KISOpenOrder("buy-1", "QQQ", "buy", 1.0, 0.0, 1.0, 19.5)
    broker = FakeKIS({}, (open_order,))

    _run(config, paths, executable, broker)

    assert [order.order_id for order in broker.cancels] == ["buy-1"]


def test_triggered_exit_uses_marketable_best_bid(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    state = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    owned = CanaryState(
        state.market_date,
        state.nonce,
        state.account_fingerprint,
        state.executable_sha256,
        StateMode.ARMED,
        "WBD",
        1,
        0,
        1,
        0,
        None,
        confirmed_entry_price_usd=Decimal("19.00"),
    )
    CanaryStateStore(paths.state).save(owned)
    broker = FakeKIS(
        {"WBD": Position("WBD", 1.0, 19.0, 20.0)},
        latest_price=20.0,
    )

    _run(config, paths, executable, broker)

    assert broker.submitted_orders[0].side == "sell"
    assert broker.submitted_orders[0].limit_price == 18.95


def test_exit_retry_uses_more_marketable_price_than_prior_attempt(tmp_path: Path) -> None:
    class HigherBidKIS(FakeKIS):
        def get_best_quote(self, symbol: str) -> dict[str, float]:
            return {
                "bid": 19.50,
                "ask": 19.55,
                "vbid1": 500.0,
                "vask1": 500.0,
            }

    paths, config, executable = _armed(tmp_path)
    state = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    owned = CanaryState(
        state.market_date,
        state.nonce,
        state.account_fingerprint,
        state.executable_sha256,
        StateMode.ARMED,
        "WBD",
        1,
        0,
        1,
        1,
        None,
        confirmed_entry_price_usd=Decimal("19.00"),
        last_exit_limit_price_usd=Decimal("19.00"),
    )
    CanaryStateStore(paths.state).save(owned)
    broker = HigherBidKIS(
        {"WBD": Position("WBD", 1.0, 19.0, 20.0)},
        latest_price=20.0,
    )

    _run(config, paths, executable, broker)

    assert broker.submitted_orders[0].limit_price is not None
    assert broker.submitted_orders[0].limit_price < 19.00


def test_expired_confirmed_position_becomes_exit_only_with_sell_lease(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    raw_arm = json.loads(paths.arm.read_text(encoding="utf-8"))
    raw_arm["issued_at"] = "2026-07-17T10:00:00+00:00"
    raw_arm["expires_at"] = "2026-07-17T11:00:00+00:00"
    paths.arm.write_text(json.dumps(raw_arm), encoding="utf-8")
    state = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    owned = CanaryState(state.market_date, state.nonce, state.account_fingerprint, state.executable_sha256, StateMode.ARMED, "QQQ", 1, 0, 1, 0, None, confirmed_entry_price_usd=Decimal("19.00"))
    CanaryStateStore(paths.state).save(owned)
    broker = FakeKIS({"QQQ": Position("QQQ", 1.0, 19.0, 19.0)})

    result = _run(config, paths, executable, broker)

    assert result.status.value == "completed"
    assert broker.posts == 0
    assert broker.leases[-1].allowed_sides == frozenset({OrderSide.SELL})
    assert CanaryStateStore(paths.state).load(expected_nonce="nonce").mode is StateMode.EXIT_ONLY


def test_runner_never_buys_outside_entry_window(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    broker = FakeKIS({})
    before_open = MarketSession(
        False,
        "before_regular_open",
        "2026-07-17T09:00:00-04:00",
        "2026-07-17T09:30:00-04:00",
        "2026-07-17T16:00:00-04:00",
    )

    result = _run(config, paths, executable, broker, before_open)

    assert result.posts == 0
    assert broker.posts == 0


def test_runner_scans_verified_universe_not_only_config_symbol(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    broker = FakeKIS({})

    result = _run(config, paths, executable, broker)

    assert result.posts == 1
    assert "WBD" in broker.universe_seen
    assert len(broker.universe_seen) > len(config.symbols)
    audit_text = paths.audit.read_text(encoding="utf-8")
    assert '"event_type":"entry_scan"' in audit_text
    assert '"selected_symbol":"WBD"' in audit_text
    persisted = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    assert persisted.get_calls_used > 0


def test_confirmed_exit_persists_cooldown_and_blocks_immediate_reentry(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    state = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    owned = CanaryState(
        state.market_date, state.nonce, state.account_fingerprint,
        state.executable_sha256, StateMode.ARMED, "WBD", 1, 0, 1, 0, None,
        confirmed_entry_price_usd=Decimal("19.00"),
    )
    pending_sell = owned.record_intent(
        OrderIntent("WBD", OrderSide.SELL, 1, Decimal("19.50"))
    ).complete_intent("sell-1", NOW)
    CanaryStateStore(paths.state).save(pending_sell)
    history = (KISOrderHistory("sell-1", "WBD", "sell", 1, 1, 19.5),)
    broker = FakeKIS({}, history=history)

    result = _run(config, paths, executable, broker)
    persisted = CanaryStateStore(paths.state).load(expected_nonce="nonce")

    assert result.posts == 0
    assert persisted.round_trips == 1
    assert persisted.cooldown_until is not None


def test_exit_only_recovers_next_session_without_a_new_buy_arm(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    fingerprint = account_fingerprint(
        config.kis.account_no, config.kis.account_product_code
    )
    recovery = CanaryState(
        "2026-07-16", "recovery-nonce", fingerprint,
        executable_sha256(executable), StateMode.EXIT_ONLY, "WBD", 1,
        1, 1, 3, None, confirmed_entry_price_usd=Decimal("19.00"),
    )
    CanaryStateStore(paths.exit_only_state).save(recovery)
    previous_paths = CanaryPaths(paths.root, "2026-07-16")
    previous_arm = json.loads(paths.arm.read_text(encoding="utf-8"))
    previous_arm["market_date"] = "2026-07-16"
    previous_arm["state_nonce"] = "recovery-nonce"
    previous_arm["issued_at"] = "2026-07-16T11:00:00+00:00"
    previous_arm["expires_at"] = "2026-07-16T20:00:00+00:00"
    previous_paths.arm.write_text(json.dumps(previous_arm), encoding="utf-8")
    paths.arm.unlink()
    paths.state.unlink()
    broker = FakeKIS({"WBD": Position("WBD", 1.0, 19.0, 19.0)})

    result = _run(config, paths, executable, broker)

    persisted = CanaryStateStore(paths.exit_only_state).load(
        expected_nonce="recovery-nonce"
    )
    assert result.status.value == "completed"
    assert broker.posts == 0
    assert broker.leases[-1].allowed_sides == frozenset({OrderSide.SELL})
    assert persisted.market_date == "2026-07-17"
    assert persisted.exit_attempts == 0


def test_exit_only_recovery_requires_its_original_bound_arm(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    state = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    forged = CanaryState(
        "2026-07-16", "forged", state.account_fingerprint,
        state.executable_sha256, StateMode.EXIT_ONLY, "WBD", 1,
        0, 1, 0, None, confirmed_entry_price_usd=Decimal("19.00"),
    )
    CanaryStateStore(paths.exit_only_state).save(forged)
    paths.arm.unlink()
    paths.state.unlink()
    broker = FakeKIS({"WBD": Position("WBD", 1.0, 19.0, 19.0)})

    result = _run(config, paths, executable, broker)

    assert result.status.value == "blocked"
    assert broker.posts == 0


def test_audit_storage_failure_blocks_before_order_post(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    paths.audit.parent.write_text("not a directory", encoding="utf-8")
    broker = FakeKIS({})

    result = _run(config, paths, executable, broker)

    assert result.status.value == "blocked"
    assert result.reason == "audit_log_unavailable"
    assert broker.posts == 0
