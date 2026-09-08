from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from .brokers.common import BrokerOrderError, BrokerRequestError
from .brokers.kis_reconciliation import KISOpenOrder
from .live_canary_audit import BoundedCanaryAuditLog
from .live_canary_operations import (
    CanaryRuntimeBlocked,
    post_order,
    require_audit,
    reserve_get_calls,
)
from .live_canary_policy import CANARY_POLICY, OrderSide
from .live_canary_pricing import CanaryExitPriceError, marketable_exit_price
from .live_canary_rules import (
    CanaryEntryContext,
    CanaryExitSnapshot,
    entry_block_reason,
    exit_reason,
)
from .live_canary_selection import DailyGetBudget, CanaryScanRequest, scan_canary_candidates
from .live_canary_state import (
    CanaryState,
    CanaryStateStore,
    JsonValue,
    OrderIntent,
)
from .market_hours import MarketSession
from .models import AccountSnapshot, OrderRequest, Position


class CanaryExecutionBroker(Protocol):
    def get_account(self, refresh: bool = False) -> AccountSnapshot: ...

    def get_overseas_buying_power(self, symbol: str, order_price: float | None = None) -> float: ...

    def get_latest_price(self, symbol: str) -> float: ...

    def get_trade_volume_universe(self, universe: set[str]) -> tuple[str, ...]: ...

    def get_price_detail(self, symbol: str) -> Mapping[str, str | int | float | None]: ...

    def get_best_quote(self, symbol: str) -> Mapping[str, str | int | float | None]: ...

    def submit_order(self, order: OrderRequest) -> Mapping[str, JsonValue]: ...

    def list_positions(self, refresh: bool = False) -> dict[str, Position]: ...

    def list_open_orders(self) -> tuple[KISOpenOrder, ...]: ...


def maybe_buy(
    state: CanaryState,
    broker: CanaryExecutionBroker,
    store: CanaryStateStore,
    symbols: frozenset[str],
    session: MarketSession,
    now: datetime,
    audit: BoundedCanaryAuditLog,
    market_date: str,
) -> tuple[CanaryState, int]:
    blocked = entry_block_reason(
        CanaryEntryContext(
            session,
            now,
            state.owned_symbol is not None,
            state.entry_attempts,
            state.round_trips,
        )
    )
    shadow_only = blocked in {
        "entry_attempt_limit_reached",
        "round_trip_limit_reached",
    }
    if blocked:
        require_audit(audit, market_date, "entry_scan_blocked", {"reason": blocked})
        if not shadow_only or not session.is_open:
            return state, 0
    if state.cooldown_until is not None and now < datetime.fromisoformat(state.cooldown_until):
        require_audit(audit, market_date, "entry_scan_blocked", {"reason": "cooldown_active"})
        return state, 0
    reserved_calls = (
        CANARY_POLICY.max_detail_get_calls
        + CANARY_POLICY.maximum_entry_auxiliary_get_calls
    )
    state = reserve_get_calls(state, store, reserved_calls)
    account = broker.get_account(refresh=True)
    budget = DailyGetBudget()
    selected = scan_canary_candidates(
        CanaryScanRequest(symbols, Decimal(str(account.cash)), budget),
        broker,
    )
    fields: dict[str, JsonValue] = {
        "reason": selected.reason,
        "ranked_symbols": list(selected.ranked_symbols),
        "inspected_symbols": list(selected.inspected_symbols),
        "get_calls": selected.get_calls,
        "reserved_get_calls": reserved_calls,
        "selected_symbol": selected.candidate.symbol if selected.candidate else None,
    }
    require_audit(audit, market_date, "entry_scan", fields)
    if shadow_only or selected.candidate is None:
        return state, 0
    candidate = selected.candidate
    fresh = broker.get_account(refresh=True)
    buying_power = broker.get_overseas_buying_power(
        candidate.symbol,
        float(candidate.entry_price),
    )
    required = candidate.entry_price + CANARY_POLICY.reserved_fee_buffer_usd
    if (
        fresh.cash < float(CANARY_POLICY.total_cash_gate_usd)
        or buying_power < float(CANARY_POLICY.total_cash_gate_usd)
        or candidate.entry_price > CANARY_POLICY.entry_limit_price_usd
        or required > CANARY_POLICY.total_cash_gate_usd
    ):
        return state, 0
    state = reserve_get_calls(
        state,
        store,
        CANARY_POLICY.maximum_reconciliation_pages * 2,
    )
    try:
        positions = broker.list_positions(refresh=True)
        open_orders = broker.list_open_orders()
    except (
        BrokerOrderError,
        BrokerRequestError,
        ConnectionError,
        OSError,
        TimeoutError,
        ValueError,
    ):
        require_audit(
            audit,
            market_date,
            "entry_scan_blocked",
            {"reason": "entry_reconciliation_get_failed"},
        )
        return state, 0
    if positions or open_orders:
        manual = state.require_manual_reconciliation()
        store.save(manual)
        require_audit(
            audit,
            market_date,
            "entry_scan_blocked",
            {"reason": "foreign_position_or_order_before_entry"},
        )
        return manual, 0
    intent = OrderIntent(
        candidate.symbol,
        OrderSide.BUY,
        CANARY_POLICY.quantity,
        candidate.entry_price,
    )
    return post_order(state, intent, broker, store, now)


def maybe_sell(
    state: CanaryState,
    broker: CanaryExecutionBroker,
    store: CanaryStateStore,
    session: MarketSession,
    now: datetime,
    audit: BoundedCanaryAuditLog,
    market_date: str,
) -> tuple[CanaryState, int]:
    if not session.is_open:
        require_audit(audit, market_date, "exit_blocked", {"reason": "market_not_open"})
        return state, 0
    if state.exit_attempts >= CANARY_POLICY.maximum_exit_attempts:
        require_audit(
            audit,
            market_date,
            "exit_blocked",
            {"reason": "exit_attempt_limit_reached"},
        )
        return state, 0
    if state.confirmed_entry_price_usd is None or state.owned_symbol is None:
        return state, 0
    state = reserve_get_calls(state, store, 1)
    current_price = Decimal(str(broker.get_latest_price(state.owned_symbol)))
    reason = exit_reason(
        CanaryExitSnapshot(
            float(state.confirmed_entry_price_usd),
            float(current_price),
            now,
            datetime.fromisoformat(session.closes_at),
        )
    )
    require_audit(
        audit,
        market_date,
        "position_tick",
        {"symbol": state.owned_symbol, "price": float(current_price), "reason": reason},
    )
    if reason == "hold":
        return state, 0
    state = reserve_get_calls(state, store, 1)
    try:
        limit_price = marketable_exit_price(
            broker.get_best_quote(state.owned_symbol),
            state.last_exit_limit_price_usd,
        )
    except CanaryExitPriceError as error:
        raise CanaryRuntimeBlocked(str(error)) from error
    intent = OrderIntent(
        state.owned_symbol,
        OrderSide.SELL,
        CANARY_POLICY.quantity,
        limit_price,
    )
    state = reserve_get_calls(
        state,
        store,
        CANARY_POLICY.maximum_reconciliation_pages,
    )
    return post_order(state, intent, broker, store, now)
