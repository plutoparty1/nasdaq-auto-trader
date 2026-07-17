from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from nasdaq_auto_trader.brokers.kis_reconciliation import (
    KISCancelOrder,
    KISCancelResult,
    KISOpenOrder,
    KISOrderHistory,
)
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.brokers.kis_client import KISCredentials
from nasdaq_auto_trader.live_canary_identity import account_fingerprint, executable_sha256
from nasdaq_auto_trader.live_canary_paths import CanaryPaths
from nasdaq_auto_trader.live_canary_policy import CANARY_POLICY, OrderSide
from nasdaq_auto_trader.live_canary_lease import BrokerLiveLease
from nasdaq_auto_trader.live_canary_state import CanaryState, CanaryStateStore, OrderIntent, StateMode
from nasdaq_auto_trader.market_hours import MarketSession
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest, Position


NOW = datetime(2026, 7, 17, 14, 0, tzinfo=UTC)
SESSION = MarketSession(True, "regular_market_open", NOW.isoformat(), "2026-07-17T09:30:00-04:00", "2026-07-17T16:00:00-04:00")


class FakeKIS:
    __slots__ = (
        "positions",
        "open_orders",
        "submit_response",
        "history",
        "posts",
        "cancels",
        "leases",
        "universe_seen",
        "latest_price",
    )

    def __init__(
        self,
        positions: dict[str, Position],
        open_orders: tuple[KISOpenOrder, ...] = (),
        submit_response: dict[str, dict[str, str]] | None = None,
        history: tuple[KISOrderHistory, ...] = (),
        latest_price: float = 19.0,
    ) -> None:
        self.positions = positions
        self.open_orders = open_orders
        self.submit_response = submit_response
        self.history = history
        self.posts = 0
        self.cancels: list[KISCancelOrder] = []
        self.leases: list[BrokerLiveLease] = []
        self.universe_seen: set[str] = set()
        self.latest_price = latest_price

    def bind_live_lease(self, lease: BrokerLiveLease) -> None: self.leases.append(lease)

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        return AccountSnapshot(25.0, 25.0, 25.0)

    def list_positions(self, refresh: bool = False) -> dict[str, Position]: return self.positions

    @contextmanager
    def reconciliation_window(self, deadline_seconds: float) -> Iterator[None]:
        del deadline_seconds
        yield

    def list_open_orders(self) -> tuple[KISOpenOrder, ...]: return self.open_orders

    def list_order_history(self, start_date: str, end_date: str) -> tuple[KISOrderHistory, ...]: return self.history

    def get_trade_volume_universe(self, universe: set[str]) -> tuple[str, ...]:
        self.universe_seen = set(universe)
        return ("WBD",) if "WBD" in universe else ()

    def get_price_detail(self, symbol: str) -> dict[str, float]: return {"last": 19.0, "volume": 600_000.0}

    def get_best_quote(self, symbol: str) -> dict[str, float]: return {"bid": 18.95, "ask": 19.0, "vbid1": 500.0, "vask1": 500.0}

    def get_overseas_buying_power(self, symbol: str, order_price: float) -> float: return 25.0

    def get_latest_price(self, symbol: str) -> float: return self.latest_price

    def submit_order(self, order: OrderRequest) -> dict[str, dict[str, str]]:
        self.posts += 1
        return self.submit_response or {"output": {"ODNO": "buy-1"}}

    def cancel_order(self, order: KISCancelOrder) -> KISCancelResult:
        self.cancels.append(order)
        return KISCancelResult(order.order_id)


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


def test_exact_known_open_order_is_cancelled_by_its_id_before_reentry(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    state = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    CanaryStateStore(paths.state).save(state.record_intent(OrderIntent("QQQ", OrderSide.BUY, 1)).complete_intent("buy-1"))
    open_order = KISOpenOrder("buy-1", "QQQ", "buy", 1.0, 0.0, 1.0, 19.5)
    broker = FakeKIS({}, (open_order,))

    _run(config, paths, executable, broker)

    assert [order.order_id for order in broker.cancels] == ["buy-1"]


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
    ).complete_intent("sell-1")
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


def _armed(tmp_path: Path) -> tuple[CanaryPaths, AppConfig, Path]:
    executable = tmp_path / "runner.exe"
    executable.write_bytes(b"runner")
    credentials = KISCredentials("app", "secret", "12345678", paper=False)
    config = AppConfig(mode="live", broker="kis", symbols=["QQQ"], allow_live_trading=True, live_environment_authorized=True, kis=credentials)
    paths = CanaryPaths(tmp_path / "canary", "2026-07-17")
    fingerprint = account_fingerprint(credentials.account_no, credentials.account_product_code)
    state = CanaryState("2026-07-17", "nonce", fingerprint, executable_sha256(executable), StateMode.ARMED, None, 0, 0, 0, 0, None)
    CanaryStateStore(paths.state).save(state)
    paths.arm.parent.mkdir(parents=True, exist_ok=True)
    paths.arm.write_text(json.dumps({"schema_version": "1", "market_date": "2026-07-17", "account_fingerprint": fingerprint, "product": "kis-real", "base_url": "https://openapi.koreainvestment.com:9443", "executable_sha256": executable_sha256(executable), "policy_digest": CANARY_POLICY.digest, "windows_sid_sha256": "b" * 64, "state_nonce": "nonce", "issued_at": "2026-07-17T11:00:00+00:00", "expires_at": "2026-07-17T23:00:00+00:00"}), encoding="utf-8")
    return paths, config, executable


def _run(
    config: AppConfig,
    paths: CanaryPaths,
    executable: Path,
    broker: FakeKIS,
    session: MarketSession = SESSION,
):
    from nasdaq_auto_trader.live_canary_runner import LiveCanaryRunRequest, run_live_canary

    return run_live_canary(LiveCanaryRunRequest(config, 1, broker, paths, executable, lambda: "b" * 64, lambda: NOW, lambda _: None, lambda _: session))
