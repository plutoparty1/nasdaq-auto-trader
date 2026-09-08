from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from .brokers.common import BrokerOrderError, BrokerRequestError
from .config import AppConfig
from .live_canary_admin import windows_sid_sha256
from .live_canary_execution import CanaryExecutionBroker
from .live_canary_identity import runtime_identity_path
from .live_canary_lease import BrokerLiveLease
from .live_canary_paths import CanaryPaths
from .live_canary_reconcile import CanaryReconciliationBroker
from .live_canary_state import CanaryState
from .market_hours import MarketSession, regular_market_session


TRANSIENT_BROKER_ERRORS: tuple[type[Exception], ...] = (
    BrokerOrderError,
    BrokerRequestError,
    ConnectionError,
    OSError,
    TimeoutError,
    ValueError,
)


class LiveCanaryStatus(StrEnum):
    COMPLETED = "completed"
    WAITING = "waiting"
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


def build_run_result(
    status: LiveCanaryStatus,
    reason: str,
    state: CanaryState | None,
    loops: int,
    cancels: int,
    posts: int = 0,
) -> LiveCanaryRunResult:
    return LiveCanaryRunResult(
        status,
        reason,
        loops,
        state.entry_attempts if state else 0,
        state.exit_attempts if state else 0,
        state.round_trips if state else 0,
        posts,
        cancels,
    )


def reconciliation_deadline_passed(
    session: MarketSession,
    now: datetime,
) -> bool:
    closes_at = datetime.fromisoformat(session.closes_at)
    return now >= closes_at + timedelta(minutes=30)
