from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from .automatic_buy_receipts import (
    OrderHistoryView,
    OriginalOrderHistory,
    RequestedQuantityHistory,
    TerminalOrderHistory,
    _order_time,
    _valid_fill,
)
from .config_settings import TradingSessionState, TradingSettings
from .market_hours import EASTERN
from .models import Bar, Position, TradeDecision
from .strategy import TechnicalStrategy

DAILY_MINIMUM_RISK_PCT: Final = 0.05


@dataclass(frozen=True, slots=True)
class DailyBuyObjective:
    due: bool
    reason: str


def daily_buy_due(
    settings: TradingSettings | None,
    state: TradingSessionState,
    now: datetime,
    history: Sequence[OrderHistoryView] | None = None,
) -> DailyBuyObjective:
    if settings is None or not settings.daily_minimum_buy_enabled:
        return DailyBuyObjective(False, "daily_minimum_disabled")
    if not settings.auto_symbol_selection_enabled or settings.order_qty != 1:
        return DailyBuyObjective(False, "daily_minimum_settings_invalid")
    if now.tzinfo is None or now.utcoffset() is None:
        return DailyBuyObjective(False, "daily_minimum_history_invalid")
    market_date = now.astimezone(EASTERN).date().isoformat()
    if settings.dry_run:
        simulated = state.market_date == market_date and state.buy_count > 0
        return DailyBuyObjective(
            not simulated,
            "daily_minimum_simulated" if simulated else "daily_minimum_simulated_due",
        )
    if history is None:
        return DailyBuyObjective(False, "daily_minimum_history_unavailable")
    filled = Decimal(0)
    seen: dict[
        tuple[str, str], tuple[str, float, float, float, str, datetime, bool]
    ] = {}
    for item in history:
        if isinstance(item, OriginalOrderHistory) and not item.is_original_order:
            continue
        if item.side == "sell":
            continue
        timestamp = _order_time(item)
        if timestamp is None:
            return DailyBuyObjective(False, "daily_minimum_history_invalid")
        if timestamp.astimezone(EASTERN).date().isoformat() != market_date:
            continue
        if timestamp > now or not item.symbol or not _valid_fill(item):
            return DailyBuyObjective(False, "daily_minimum_history_invalid")
        status = item.status if isinstance(item, TerminalOrderHistory) else ""
        quantity_known = (
            not isinstance(item, RequestedQuantityHistory) or item.requested_quantity_known
        )
        identity = (item.order_id, market_date)
        values = (
            item.symbol, item.quantity, item.filled_quantity,
            item.average_fill_price, status, timestamp, quantity_known,
        )
        if identity in seen:
            if seen[identity] != values:
                return DailyBuyObjective(False, "daily_minimum_history_invalid")
            continue
        seen[identity] = values
        terminal = status in {"canceled", "cancelled", "rejected", "expired"}
        fully_filled = (
            status == "filled" and item.filled_quantity > 0
            and (not quantity_known or item.filled_quantity == item.quantity)
        )
        if not (terminal or fully_filled):
            return DailyBuyObjective(False, "daily_minimum_history_unresolved")
        filled += Decimal(str(item.filled_quantity))
    if filled >= 1:
        return DailyBuyObjective(False, "daily_minimum_buy_filled")
    return DailyBuyObjective(True, "daily_minimum_due")


def daily_minimum_decision(
    strategy: TechnicalStrategy,
    decision: TradeDecision,
    bars: list[Bar],
    position: Position | None,
    *,
    due: bool,
) -> TradeDecision:
    return decision
