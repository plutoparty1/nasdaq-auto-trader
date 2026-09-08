from __future__ import annotations

from dataclasses import dataclass, field, replace

from .models import PositionHighWater
from .session_safety_policy import SessionSafetyPolicyError, safety_block_reason
from .session_state_codec import (
    SessionStateCodecError,
    parsed_market_date,
    required_market_date,
)


class SafetyReservationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PersistedSafetyState:
    market_date: str = ""
    buy_count: int = 0
    sell_count: int = 0
    last_order_at: str = ""
    daily_loss_breached: bool = False
    baseline_observed: bool = False
    position_high_water: dict[str, PositionHighWater] = field(default_factory=dict)
    closed_position_symbols: tuple[str, ...] = ()
    position_state_versions: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SafetyReservationRequest:
    market_date: str
    side: str
    timestamp: str
    max_daily_buy_count: int
    max_daily_sell_count: int
    cooldown_minutes: int
    daily_loss_breached: bool
    daily_loss_state_unavailable: bool
    baseline_available: bool
    max_daily_order_count: int = 2**31 - 1


@dataclass(frozen=True, slots=True)
class SafetyReservationDecision:
    granted: bool
    reason: str = ""


def reserve_safety_state(
    safety: PersistedSafetyState,
    request: SafetyReservationRequest,
) -> tuple[PersistedSafetyState, SafetyReservationDecision]:
    try:
        persisted_date = parsed_market_date(safety.market_date)
        requested_date = required_market_date(request.market_date)
    except SessionStateCodecError as exc:
        raise SafetyReservationError from exc
    if persisted_date is not None and requested_date < persisted_date:
        return safety, SafetyReservationDecision(
            False,
            "session_market_date_regression",
        )
    if persisted_date != requested_date:
        safety = PersistedSafetyState(
            market_date=request.market_date,
            position_high_water=dict(safety.position_high_water),
            closed_position_symbols=safety.closed_position_symbols,
            position_state_versions=dict(safety.position_state_versions),
        )
    if request.daily_loss_breached and not safety.daily_loss_breached:
        safety = replace(
            safety,
            daily_loss_breached=True,
            baseline_observed=True,
        )
    try:
        reason = safety_block_reason(safety, request)
    except SessionSafetyPolicyError as exc:
        raise SafetyReservationError from exc
    if reason:
        return safety, SafetyReservationDecision(False, reason)
    reserved = replace(
        safety,
        buy_count=safety.buy_count + (1 if request.side == "buy" else 0),
        sell_count=safety.sell_count + (1 if request.side == "sell" else 0),
        last_order_at=request.timestamp,
        baseline_observed=safety.baseline_observed or request.baseline_available,
    )
    return reserved, SafetyReservationDecision(True)
