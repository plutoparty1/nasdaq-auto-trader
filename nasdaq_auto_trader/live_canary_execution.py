from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol

from .brokers.common import BrokerOrderError, BrokerRequestError
from .live_canary_audit import BoundedCanaryAuditLog, CanaryAuditEvent
from .live_canary_policy import CANARY_POLICY, OrderSide
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
    CanaryStateTransitionError,
    JsonValue,
    OrderIntent,
)
from .market_hours import MarketSession
from .models import AccountSnapshot, OrderRequest


class CanaryExecutionBroker(Protocol):
    def get_account(self, refresh: bool = False) -> AccountSnapshot: ...

    def get_overseas_buying_power(self, symbol: str, order_price: float | None = None) -> float: ...

    def get_latest_price(self, symbol: str) -> float: ...

    def get_trade_volume_universe(self, universe: set[str]) -> tuple[str, ...]: ...

    def get_price_detail(self, symbol: str) -> Mapping[str, str | int | float | None]: ...

    def get_best_quote(self, symbol: str) -> Mapping[str, str | int | float | None]: ...

    def submit_order(self, order: OrderRequest) -> Mapping[str, JsonValue]: ...


@dataclass(frozen=True, slots=True)
class CanaryRuntimeBlocked(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


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
    intent = OrderIntent(
        candidate.symbol,
        OrderSide.BUY,
        CANARY_POLICY.quantity,
        candidate.entry_price,
    )
    return post_order(state, intent, broker, store)


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
    intent = OrderIntent(
        state.owned_symbol,
        OrderSide.SELL,
        CANARY_POLICY.quantity,
        current_price,
    )
    return post_order(state, intent, broker, store)


def post_order(
    state: CanaryState,
    intent: OrderIntent,
    broker: CanaryExecutionBroker,
    store: CanaryStateStore,
) -> tuple[CanaryState, int]:
    try:
        pending = state.record_intent(intent)
    except CanaryStateTransitionError as error:
        raise CanaryRuntimeBlocked(str(error)) from error
    store.save(pending)
    try:
        response = broker.submit_order(
            OrderRequest(
                intent.symbol,
                intent.side.value,
                "limit",
                "day",
                float(intent.quantity),
                None,
                float(intent.limit_price_usd),
            )
        )
        order_id = exact_kis_odno(response)
    except (
        AttributeError,
        BrokerOrderError,
        BrokerRequestError,
        ConnectionError,
        OSError,
        TimeoutError,
        TypeError,
        ValueError,
    ):
        manual = pending.require_manual_reconciliation()
        store.save(manual)
        return manual, 1
    if not order_id:
        manual = pending.require_manual_reconciliation()
        store.save(manual)
        return manual, 1
    completed = pending.complete_intent(order_id)
    store.save(completed)
    return completed, 1


def reserve_reconciliation_gets(
    state: CanaryState,
    store: CanaryStateStore,
) -> CanaryState:
    return reserve_get_calls(
        state,
        store,
        CANARY_POLICY.maximum_reconciliation_pages * 3,
    )


def reserve_get_calls(
    state: CanaryState,
    store: CanaryStateStore,
    count: int,
) -> CanaryState:
    next_used = state.get_calls_used + count
    if count < 0 or next_used > CANARY_POLICY.daily_get_budget:
        raise CanaryRuntimeBlocked("daily_get_budget_exhausted")
    updated = state.with_get_calls_used(next_used)
    store.save(updated)
    return updated


def apply_exit_cooldown(
    previous_round_trips: int,
    state: CanaryState,
    now: datetime,
) -> CanaryState:
    if state.round_trips <= previous_round_trips:
        return state
    until = now + timedelta(minutes=CANARY_POLICY.cooldown_minutes)
    return state.with_cooldown_until(until.isoformat())


def exact_kis_odno(payload: Mapping[str, JsonValue]) -> str:
    output = payload.get("output")
    if not isinstance(output, dict):
        return ""
    order_id = output.get("ODNO")
    return order_id if isinstance(order_id, str) and order_id else ""


def require_audit(
    audit: BoundedCanaryAuditLog,
    market_date: str,
    event_type: str,
    fields: Mapping[str, JsonValue],
) -> None:
    if not audit.append(CanaryAuditEvent(market_date, event_type, fields)):
        raise CanaryRuntimeBlocked("audit_log_unavailable")
