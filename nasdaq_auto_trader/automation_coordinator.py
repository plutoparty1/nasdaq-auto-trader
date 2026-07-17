from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from .market_hours import regular_market_session
from .operating_state import OperatingState, OperatingStateStore, RuntimeState


@dataclass(frozen=True, slots=True)
class PreflightHealth:
    model_ok: bool = True
    market_data_ok: bool = True
    broker_ok: bool = True
    account_ok: bool = True
    positions_ok: bool = True
    risk_config_ok: bool = True
    clock_ok: bool = True

    def blocking_reason(self) -> str:
        checks = (
            (self.market_data_ok, "market_data_unavailable"),
            (self.broker_ok, "broker_unavailable"),
            (self.account_ok, "account_state_unavailable"),
            (self.positions_ok, "position_state_mismatch"),
            (self.risk_config_ok, "risk_config_invalid"),
            (self.clock_ok, "system_clock_invalid"),
            (self.model_ok, "operating_model_unavailable"),
        )
        return next((reason for healthy, reason in checks if not healthy), "")

    def shadow_scan_ready(self) -> bool:
        return all(
            (
                self.market_data_ok,
                self.broker_ok,
                self.account_ok,
                self.positions_ok,
                self.risk_config_ok,
                self.clock_ok,
            )
        )


@dataclass(frozen=True, slots=True)
class TransitionResult:
    state: OperatingState
    reason: str


class AutomationCoordinator:
    def __init__(self, store: OperatingStateStore) -> None:
        self.store = store

    def advance(
        self,
        now: datetime,
        health: PreflightHealth,
        *,
        reconciliation_complete: bool = True,
        new_data_available: bool = False,
        emergency_stop: bool = False,
    ) -> TransitionResult:
        if emergency_stop:
            return self._transition(OperatingState.EMERGENCY_STOP, "emergency_stop_requested", now)
        session = regular_market_session(now)
        blocking_reason = health.blocking_reason()
        if session.reason == "before_regular_open" and new_data_available:
            return self._transition(
                OperatingState.OFF_HOURS_LEARNING,
                "missed_learning_before_open",
                now,
            )
        if session.reason == "before_regular_open":
            return self._transition(OperatingState.PRE_MARKET_CHECK, session.reason, now)
        if (
            session.is_open
            and blocking_reason == "operating_model_unavailable"
            and health.shadow_scan_ready()
        ):
            return self._transition(
                OperatingState.INTRADAY_SHADOW_SCAN,
                blocking_reason,
                now,
            )
        if blocking_reason and session.is_open:
            return self._transition(OperatingState.SAFE_HALT, blocking_reason, now)
        if session.is_open:
            return self._transition(OperatingState.LIVE_TRADING, "preflight_passed", now)
        if session.reason == "after_regular_close" and not reconciliation_complete:
            return self._transition(
                OperatingState.POST_MARKET_RECONCILIATION,
                "reconciliation_required",
                now,
            )
        if new_data_available:
            return self._transition(OperatingState.OFF_HOURS_LEARNING, "new_data_available", now)
        return self._transition(OperatingState.IDLE, session.reason, now)

    def safe_halt(self, reason: str, now: datetime) -> TransitionResult:
        return self._transition(OperatingState.SAFE_HALT, reason, now)

    def _transition(
        self,
        target: OperatingState,
        reason: str,
        now: datetime,
    ) -> TransitionResult:
        current = self.store.load()
        entered_at = now.astimezone(timezone.utc)
        state = replace(current, state=target, entered_at=entered_at)
        self.store.save(state)
        return TransitionResult(target, reason)
