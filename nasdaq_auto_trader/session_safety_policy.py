from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol


class SafetyStateView(Protocol):
    buy_count: int
    sell_count: int
    last_order_at: str
    daily_loss_breached: bool
    baseline_observed: bool


class SafetyRequestView(Protocol):
    side: str
    timestamp: str
    max_daily_buy_count: int
    max_daily_sell_count: int
    max_daily_order_count: int
    cooldown_minutes: int
    daily_loss_breached: bool
    daily_loss_state_unavailable: bool
    baseline_available: bool


def safety_block_reason(
    safety: SafetyStateView,
    request: SafetyRequestView,
) -> str:
    if request.side not in ("buy", "sell"):
        return "safety_reservation_side_invalid"
    if safety.buy_count + safety.sell_count >= request.max_daily_order_count:
        return "learned_daily_order_limit_reached"
    if request.side == "buy":
        if safety.daily_loss_breached or request.daily_loss_breached:
            return "max_daily_loss_reached"
        if request.daily_loss_state_unavailable or (
            safety.baseline_observed and not request.baseline_available
        ):
            return "daily_loss_state_unavailable"
        if safety.buy_count >= request.max_daily_buy_count:
            return "max_daily_buy_count_reached"
    if request.side == "sell" and safety.sell_count >= request.max_daily_sell_count:
        return "max_daily_sell_count_reached"
    if request.cooldown_minutes <= 0 or not safety.last_order_at:
        return ""
    try:
        previous = datetime.fromisoformat(safety.last_order_at)
        current = datetime.fromisoformat(request.timestamp)
    except ValueError as exc:
        raise SessionSafetyPolicyError("session_store_corrupt") from exc
    if current < previous + timedelta(minutes=request.cooldown_minutes):
        return "cooldown_active"
    return ""


class SessionSafetyPolicyError(ValueError):
    pass
