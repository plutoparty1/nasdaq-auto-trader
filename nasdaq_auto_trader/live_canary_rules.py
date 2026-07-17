from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .live_canary_policy import CANARY_POLICY
from .market_hours import MarketSession


CanaryExitReason = Literal["take_profit", "stop_loss", "force_exit", "hold"]


@dataclass(frozen=True, slots=True)
class CanaryRuleError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class CanaryEntryContext:
    session: MarketSession
    now: datetime
    has_position: bool
    entry_attempts: int
    round_trips: int


@dataclass(frozen=True, slots=True)
class CanaryExitSnapshot:
    entry_price: float
    current_price: float
    now: datetime
    closes_at: datetime


def entry_block_reason(context: CanaryEntryContext) -> str:
    if context.has_position:
        return "canary_position_active"
    if context.entry_attempts >= CANARY_POLICY.maximum_entry_attempts:
        return "entry_attempt_limit_reached"
    if context.round_trips >= CANARY_POLICY.maximum_round_trips:
        return "round_trip_limit_reached"
    if not context.session.is_open:
        return f"market_not_open:{context.session.reason}"
    opens_at = datetime.fromisoformat(context.session.opens_at)
    closes_at = datetime.fromisoformat(context.session.closes_at)
    if context.now < opens_at + timedelta(
        minutes=CANARY_POLICY.entry_window_open_minutes
    ):
        return "entry_window_not_open"
    if context.now >= closes_at - timedelta(
        minutes=CANARY_POLICY.entry_window_close_minutes
    ):
        return "entry_window_closed"
    return ""


def exit_reason(snapshot: CanaryExitSnapshot) -> CanaryExitReason:
    if snapshot.entry_price <= 0 or snapshot.current_price <= 0:
        raise CanaryRuleError("canary_exit_price_invalid")
    pnl_ratio = snapshot.current_price / snapshot.entry_price
    if pnl_ratio >= 1.0 + float(CANARY_POLICY.take_profit_rate):
        return "take_profit"
    if pnl_ratio <= 1.0 + float(CANARY_POLICY.stop_loss_rate):
        return "stop_loss"
    if snapshot.now >= snapshot.closes_at - timedelta(
        minutes=CANARY_POLICY.forced_exit_close_minutes
    ):
        return "force_exit"
    return "hold"
