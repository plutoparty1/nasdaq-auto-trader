from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from nasdaq_auto_trader.live_canary_paths import CanaryPaths
from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.live_canary_policy import CANARY_POLICY
from nasdaq_auto_trader.live_canary_state import CanaryState, CanaryStateStore, StateMode
from nasdaq_auto_trader.market_hours import MarketSession
from nasdaq_auto_trader.models import OrderRequest, Position
from tests.test_live_canary_runner import FakeKIS, _armed, _run


class MalformedBrokerResponse(ValueError):
    pass


class MalformedPostKIS(FakeKIS):
    __slots__ = ()

    def submit_order(self, order: OrderRequest) -> dict[str, dict[str, str]]:
        self.posts += 1
        raise MalformedBrokerResponse("malformed JSON response")


class PositionPollFailureKIS(FakeKIS):
    def __init__(self, positions: dict[str, Position]) -> None:
        super().__init__(positions)
        self.position_reads = 0

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        self.position_reads += 1
        if self.position_reads > 1:
            raise BrokerRequestError("position page failed")
        return super().list_positions(refresh=refresh)


def test_exit_attempt_limit_returns_safely_without_post(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    _save_owned(paths, exit_attempts=CANARY_POLICY.maximum_exit_attempts)
    broker = FakeKIS(
        {"WBD": Position("WBD", 1.0, 19.0, 20.0)},
        latest_price=20.0,
    )

    result = _run(config, paths, executable, broker)

    assert result.status.value == "completed"
    assert result.posts == 0
    assert broker.posts == 0


def test_owned_position_never_sells_before_open(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    _save_owned(paths)
    broker = FakeKIS(
        {"WBD": Position("WBD", 1.0, 19.0, 20.0)},
        latest_price=20.0,
    )
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


def test_owned_position_never_sells_after_close(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    _save_owned(paths)
    broker = FakeKIS(
        {"WBD": Position("WBD", 1.0, 19.0, 20.0)},
        latest_price=20.0,
    )
    after_close = MarketSession(
        False,
        "after_regular_close",
        "2026-07-17T16:01:00-04:00",
        "2026-07-17T09:30:00-04:00",
        "2026-07-17T16:00:00-04:00",
    )

    result = _run(config, paths, executable, broker, after_close)

    assert result.posts == 0
    assert broker.posts == 0


def test_malformed_post_response_enters_permanent_manual_state(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    broker = MalformedPostKIS({})

    result = _run(config, paths, executable, broker)

    persisted = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    assert result.status.value == "manual_reconciliation_required"
    assert broker.posts == 1
    assert persisted.mode is StateMode.MANUAL_RECONCILIATION_REQUIRED


def test_durable_get_budget_blocks_before_reconciliation_reads(tmp_path: Path) -> None:
    paths, config, executable = _armed(tmp_path)
    state = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    CanaryStateStore(paths.state).save(
        state.with_get_calls_used(
            CANARY_POLICY.daily_get_budget
            - CANARY_POLICY.maximum_reconciliation_pages
        )
    )
    broker = FakeKIS({})

    result = _run(config, paths, executable, broker)

    assert result.status.value == "blocked"
    assert result.reason == "daily_get_budget_exhausted"
    assert broker.posts == 0


def test_position_poll_failure_is_durable_and_reserves_all_pages(
    tmp_path: Path,
) -> None:
    paths, config, executable = _armed(tmp_path)
    _save_owned(paths)
    broker = PositionPollFailureKIS(
        {"WBD": Position("WBD", 1.0, 19.0, 20.0)}
    )

    result = _run(config, paths, executable, broker)

    persisted = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    assert result.reason == "position_get_failed"
    assert persisted.mode is StateMode.MANUAL_RECONCILIATION_REQUIRED
    assert persisted.get_calls_used == (
        CANARY_POLICY.maximum_reconciliation_pages * 4
    )
    assert broker.posts == 0


def test_shadow_scan_continues_after_round_trip_cap_without_post(
    tmp_path: Path,
) -> None:
    paths, config, executable = _armed(tmp_path)
    state = CanaryStateStore(paths.state).load(expected_nonce="nonce")
    capped = CanaryState(
        state.market_date,
        state.nonce,
        state.account_fingerprint,
        state.executable_sha256,
        StateMode.ARMED,
        None,
        0,
        CANARY_POLICY.maximum_round_trips,
        CANARY_POLICY.maximum_entry_attempts,
        0,
        None,
    )
    CanaryStateStore(paths.state).save(capped)
    broker = FakeKIS({})

    result = _run(config, paths, executable, broker)

    assert result.posts == 0
    assert broker.posts == 0
    assert "WBD" in broker.universe_seen
    assert '"event_type":"entry_scan"' in paths.audit.read_text(encoding="utf-8")


def _save_owned(paths: CanaryPaths, exit_attempts: int = 0) -> None:
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
        exit_attempts,
        None,
        confirmed_entry_price_usd=Decimal("19.00"),
    )
    CanaryStateStore(paths.state).save(owned)
