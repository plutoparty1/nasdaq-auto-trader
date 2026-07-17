from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from enum import StrEnum
import hashlib
from typing import Final


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class CanaryPolicy:
    policy_id: str
    entry_limit_price_usd: Decimal
    reserved_fee_buffer_usd: Decimal
    total_cash_gate_usd: Decimal
    quantity: int
    maximum_round_trips: int
    maximum_entry_attempts: int
    maximum_exit_attempts: int
    take_profit_rate: Decimal
    stop_loss_rate: Decimal
    entry_window_open_minutes: int
    entry_window_close_minutes: int
    forced_exit_close_minutes: int
    cooldown_minutes: int
    entry_scan_interval_minutes: int
    price_poll_interval_seconds: int
    position_poll_interval_seconds: int
    max_scan_symbols: int
    max_get_timeout_seconds: int
    maximum_get_retries: int
    scan_wall_budget_seconds: int
    rank_top_symbols: int
    deep_inspect_symbols: int
    max_detail_get_calls: int
    daily_get_budget: int
    reconciliation_tick_deadline_seconds: int
    maximum_reconciliation_pages: int
    maximum_entry_auxiliary_get_calls: int

    @property
    def digest(self) -> str:
        canonical = "|".join(str(getattr(self, field.name)) for field in fields(self))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


CANARY_POLICY: Final = CanaryPolicy(
    policy_id="bounded-live-canary-v1",
    entry_limit_price_usd=Decimal("19.50"),
    reserved_fee_buffer_usd=Decimal("0.50"),
    total_cash_gate_usd=Decimal("20.00"),
    quantity=1,
    maximum_round_trips=3,
    maximum_entry_attempts=3,
    maximum_exit_attempts=3,
    take_profit_rate=Decimal("0.05"), stop_loss_rate=Decimal("-0.05"),
    entry_window_open_minutes=15, entry_window_close_minutes=30, forced_exit_close_minutes=15,
    cooldown_minutes=30, entry_scan_interval_minutes=15, price_poll_interval_seconds=15,
    position_poll_interval_seconds=60, max_scan_symbols=20, max_get_timeout_seconds=8,
    maximum_get_retries=2, scan_wall_budget_seconds=120,
    rank_top_symbols=30, deep_inspect_symbols=10, max_detail_get_calls=20,
    daily_get_budget=6000, reconciliation_tick_deadline_seconds=10,
    maximum_reconciliation_pages=10,
    maximum_entry_auxiliary_get_calls=6,
)
