from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from .brokers.common import BrokerOrderError, BrokerRequestError
from .brokers.kis_client import KISClient
from .config import AppConfig
from .file_lock import FileLockTimeout, exclusive_file_lock
from .live_canary_admin import windows_sid_sha256
from .live_canary_audit import BoundedCanaryAuditLog
from .live_canary_arm import ArmEnvelope, ArmEnvelopeError, ArmValidationContext
from .live_canary_execution import (
    CanaryExecutionBroker,
    CanaryRuntimeBlocked,
    apply_exit_cooldown,
    maybe_buy,
    maybe_sell,
    require_audit,
    reserve_get_calls,
    reserve_reconciliation_gets,
)
from .live_canary_identity import (
    account_fingerprint,
    executable_sha256,
    runtime_identity_path,
)
from .live_canary_lease import BrokerLeaseError, BrokerLiveLease
from .live_canary_paths import CanaryPaths
from .live_canary_policy import CANARY_POLICY, OrderSide
from .live_canary_reconcile import CanaryReconciliationBroker, ReconciliationResult, owned_position_matches, reconcile_startup
from .live_canary_runtime import (
    canary_universe,
    config_error,
    expire_state,
    load_envelope,
    load_exit_only_recovery,
    recovery_envelope,
    validate_envelope,
)
from .live_canary_state import (
    CanaryState,
    CanaryStateCorruptError,
    CanaryStateStore,
    CanaryStateTransitionError,
    StateMode,
)
from .market_hours import MarketSession, regular_market_session


class LiveCanaryStatus(StrEnum):
    COMPLETED = "completed"
    STOPPED = "stopped"
    BLOCKED = "blocked"
    MANUAL_RECONCILIATION_REQUIRED = "manual_reconciliation_required"


class LiveCanaryBroker(
    CanaryReconciliationBroker,
    CanaryExecutionBroker,
    Protocol,
):
    def bind_live_lease(self, lease: BrokerLiveLease) -> None: ...


@dataclass(frozen=True, slots=True)
class LiveCanaryRunRequest:
    config: AppConfig
    max_loops: int | None = None
    broker: LiveCanaryBroker | None = None
    paths: CanaryPaths | None = None
    executable: Path = field(default_factory=runtime_identity_path)
    sid_sha256: Callable[[], str] = windows_sid_sha256
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    sleeper: Callable[[float], None] = time.sleep
    session_provider: Callable[[datetime], MarketSession] = regular_market_session


@dataclass(frozen=True, slots=True)
class LiveCanaryRunResult:
    status: LiveCanaryStatus
    reason: str
    loops: int
    entry_attempts: int
    exit_attempts: int
    round_trips: int
    posts: int
    cancels: int


def run_live_canary(request: LiveCanaryRunRequest) -> LiveCanaryRunResult:
    now = request.clock()
    error_reason = config_error(request.config)
    if error_reason:
        return _result(LiveCanaryStatus.BLOCKED, error_reason, None, 0, 0)
    market_date = request.session_provider(now).market_time[:10]
    paths = request.paths or CanaryPaths.for_market_date(market_date)
    fingerprint = account_fingerprint(
        request.config.kis.account_no,
        request.config.kis.account_product_code,
    )
    executable_digest = executable_sha256(request.executable)
    try:
        if paths.arm.exists():
            envelope = load_envelope(paths.arm)
            context = ArmValidationContext(market_date, fingerprint, "kis-real", KISClient.real_base_url, executable_digest, CANARY_POLICY.digest, request.sid_sha256(), now)
            validate_envelope(envelope, context)
            state = CanaryStateStore(paths.state).load(expected_nonce=envelope.state_nonce)
        else:
            state = load_exit_only_recovery(
                paths,
                market_date,
                fingerprint,
                executable_digest,
                request.sid_sha256(),
            )
            envelope = recovery_envelope(state, request.sid_sha256(), now)
            context = ArmValidationContext(market_date, fingerprint, "kis-real", KISClient.real_base_url, executable_digest, CANARY_POLICY.digest, request.sid_sha256(), now)
    except (ArmEnvelopeError, CanaryStateCorruptError, OSError, CanaryStateTransitionError) as error:
        return _result(LiveCanaryStatus.BLOCKED, str(error), None, 0, 0)
    if (state.market_date, state.account_fingerprint, state.executable_sha256) != (market_date, fingerprint, context.executable_sha256):
        return _result(LiveCanaryStatus.BLOCKED, "durable_state_binding_mismatch", state, 0, 0)
    broker = request.broker or KISClient(request.config.kis)
    allowed_sides = frozenset({OrderSide.SELL}) if state.mode is StateMode.EXIT_ONLY else frozenset({OrderSide.BUY, OrderSide.SELL})
    try:
        with exclusive_file_lock(paths.process_lock, 0.05):
            with BrokerLiveLease.acquire(paths.broker_lock, fingerprint, allowed_sides) as lease:
                broker.bind_live_lease(lease)
                try:
                    return _run_locked(request, broker, paths, envelope, state, market_date, lease)
                except CanaryRuntimeBlocked as error:
                    return _result(LiveCanaryStatus.BLOCKED, error.reason, state, 0, 0)
    except (FileLockTimeout, BrokerLeaseError) as error:
        return _result(LiveCanaryStatus.BLOCKED, str(error), state, 0, 0)


def _run_locked(request: LiveCanaryRunRequest, broker: LiveCanaryBroker, paths: CanaryPaths, envelope: ArmEnvelope, state: CanaryState, market_date: str, lease: BrokerLiveLease) -> LiveCanaryRunResult:
    stable_exit_store = CanaryStateStore(paths.exit_only_state)
    store = stable_exit_store if state.mode is StateMode.EXIT_ONLY else CanaryStateStore(paths.state)
    audit = BoundedCanaryAuditLog(paths.audit.parent)
    if state.mode is StateMode.MANUAL_RECONCILIATION_REQUIRED:
        return _result(LiveCanaryStatus.MANUAL_RECONCILIATION_REQUIRED, "durable_manual_reconciliation_required", state, 0, 0)
    prior_round_trips = state.round_trips
    try:
        state = reserve_reconciliation_gets(state, store)
        reconciliation = reconcile_startup(state, broker, market_date)
    except (BrokerOrderError, BrokerRequestError, ConnectionError, OSError, TimeoutError, ValueError):
        reconciliation = ReconciliationResult(state.require_manual_reconciliation(), "startup_get_failed")
    state = reconciliation.state
    state = apply_exit_cooldown(prior_round_trips, state, request.clock())
    store.save(state)
    require_audit(audit, market_date, "startup_reconciliation", {"reason": reconciliation.reason})
    if reconciliation.manual_required:
        return _result(LiveCanaryStatus.MANUAL_RECONCILIATION_REQUIRED, reconciliation.reason, state, 0, reconciliation.cancelled_orders)
    if state.mode is StateMode.COMPLETED:
        return _result(LiveCanaryStatus.STOPPED, "exit_only_completed", state, 0, reconciliation.cancelled_orders)
    next_scan = request.clock()
    next_position_check = next_scan
    universe = canary_universe(request.config.symbols)
    loops = posts = 0
    while request.max_loops is None or loops < request.max_loops:
        now = request.clock()
        loops += 1
        if state.known_order is not None:
            prior_round_trips = state.round_trips
            try:
                state = reserve_reconciliation_gets(state, store)
                reconciliation = reconcile_startup(state, broker, market_date)
            except (BrokerOrderError, BrokerRequestError, ConnectionError, OSError, TimeoutError, ValueError):
                reconciliation = ReconciliationResult(state.require_manual_reconciliation(), "known_order_get_failed")
            state = reconciliation.state
            state = apply_exit_cooldown(prior_round_trips, state, now)
            store.save(state)
            if state.mode is not StateMode.ARMED:
                stable_exit_store.save(state)
            if reconciliation.manual_required:
                return _result(LiveCanaryStatus.MANUAL_RECONCILIATION_REQUIRED, reconciliation.reason, state, loops, reconciliation.cancelled_orders, posts)
            if state.mode is StateMode.COMPLETED:
                return _result(LiveCanaryStatus.STOPPED, "exit_only_completed", state, loops, reconciliation.cancelled_orders, posts)
        expired = now.astimezone(UTC) >= envelope.expires_at
        if expired:
            state, terminal = expire_state(state, store, stable_exit_store)
            if terminal:
                return _result(LiveCanaryStatus.STOPPED, "arm_expired", state, loops, reconciliation.cancelled_orders, posts)
            broker.bind_live_lease(replace(lease, allowed_sides=frozenset({OrderSide.SELL})))
        session = request.session_provider(now)
        if state.owned_symbol is not None:
            if now >= next_position_check:
                try:
                    state = reserve_get_calls(
                        state,
                        store,
                        CANARY_POLICY.maximum_reconciliation_pages,
                    )
                    positions = broker.list_positions(refresh=True)
                except (
                    BrokerOrderError,
                    BrokerRequestError,
                    ConnectionError,
                    OSError,
                    TimeoutError,
                    ValueError,
                ):
                    state = state.require_manual_reconciliation()
                    store.save(state)
                    stable_exit_store.save(state)
                    return _result(
                        LiveCanaryStatus.MANUAL_RECONCILIATION_REQUIRED,
                        "position_get_failed",
                        state,
                        loops,
                        reconciliation.cancelled_orders,
                        posts,
                    )
                if not owned_position_matches(state, positions):
                    state = state.require_manual_reconciliation()
                    store.save(state)
                    stable_exit_store.save(state)
                    return _result(LiveCanaryStatus.MANUAL_RECONCILIATION_REQUIRED, "position_reconciliation_failed", state, loops, reconciliation.cancelled_orders, posts)
                next_position_check = now + timedelta(seconds=CANARY_POLICY.position_poll_interval_seconds)
            state, posted = maybe_sell(
                state, broker, store, session, now, audit, market_date
            )
            if state.mode is not StateMode.ARMED:
                stable_exit_store.save(state)
            posts += posted
            if state.mode is StateMode.MANUAL_RECONCILIATION_REQUIRED:
                return _result(LiveCanaryStatus.MANUAL_RECONCILIATION_REQUIRED, "sell_post_outcome_unknown", state, loops, reconciliation.cancelled_orders, posts)
        elif now >= next_scan and state.mode is StateMode.ARMED:
            state, posted = maybe_buy(
                state, broker, store, universe, session, now, audit, market_date
            )
            store.save(state)
            posts += posted
            next_scan = now + timedelta(minutes=CANARY_POLICY.entry_scan_interval_minutes)
            if state.mode is StateMode.MANUAL_RECONCILIATION_REQUIRED:
                return _result(LiveCanaryStatus.MANUAL_RECONCILIATION_REQUIRED, "buy_post_outcome_unknown", state, loops, reconciliation.cancelled_orders, posts)
        if request.max_loops is None or loops < request.max_loops:
            request.sleeper(CANARY_POLICY.price_poll_interval_seconds)
    return _result(LiveCanaryStatus.COMPLETED, "max_loops_reached", state, loops, reconciliation.cancelled_orders, posts)


def _result(status: LiveCanaryStatus, reason: str, state: CanaryState | None, loops: int, cancels: int, posts: int = 0) -> LiveCanaryRunResult:
    return LiveCanaryRunResult(status, reason, loops, state.entry_attempts if state else 0, state.exit_attempts if state else 0, state.round_trips if state else 0, posts, cancels)
