from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from .brokers.common import BrokerOrderError, BrokerRequestError
from .live_canary_audit import BoundedCanaryAuditLog, CanaryAuditEvent
from .live_canary_policy import CANARY_POLICY
from .live_canary_state import (
    CanaryState,
    CanaryStateStore,
    CanaryStateTransitionError,
    JsonValue,
    OrderIntent,
)
from .models import OrderRequest


class CanaryOrderBroker(Protocol):
    def submit_order(self, order: OrderRequest) -> Mapping[str, JsonValue]: ...


@dataclass(frozen=True, slots=True)
class CanaryRuntimeBlocked(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def post_order(
    state: CanaryState,
    intent: OrderIntent,
    broker: CanaryOrderBroker,
    store: CanaryStateStore,
    now: datetime,
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
        order_id = _exact_kis_odno(response)
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
    completed = pending.complete_intent(order_id, now)
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


def require_audit(
    audit: BoundedCanaryAuditLog,
    market_date: str,
    event_type: str,
    fields: Mapping[str, JsonValue],
) -> None:
    if not audit.append(CanaryAuditEvent(market_date, event_type, fields)):
        raise CanaryRuntimeBlocked("audit_log_unavailable")


def _exact_kis_odno(payload: Mapping[str, JsonValue]) -> str:
    output = payload.get("output")
    if not isinstance(output, dict):
        return ""
    order_id = output.get("ODNO")
    return order_id if isinstance(order_id, str) and order_id else ""
