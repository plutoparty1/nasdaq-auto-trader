from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import TypeAlias, assert_never

from .live_canary_policy import CANARY_POLICY, OrderSide

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

class StateMode(StrEnum):
    ARMED = "armed"
    EXIT_ONLY = "exit_only"
    MANUAL_RECONCILIATION_REQUIRED = "manual_reconciliation_required"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class CanaryStateCorruptError(Exception):
    reason: str

    def __str__(self) -> str:
        return f"live-canary state is unusable: {self.reason}"


@dataclass(frozen=True, slots=True)
class CanaryStateTransitionError(Exception):
    reason: str

    def __str__(self) -> str:
        return f"live-canary transition rejected: {self.reason}"


@dataclass(frozen=True, slots=True)
class OrderIntent:
    symbol: str
    side: OrderSide
    quantity: int
    limit_price_usd: Decimal = CANARY_POLICY.entry_limit_price_usd

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.upper(): raise CanaryStateTransitionError("symbol must be non-empty uppercase text")
        if self.quantity != CANARY_POLICY.quantity: raise CanaryStateTransitionError("quantity must equal fixed canary quantity")
        if self.limit_price_usd <= 0: raise CanaryStateTransitionError("limit price must be positive")


@dataclass(frozen=True, slots=True)
class KnownOrder:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    limit_price_usd: Decimal
    submitted_at: str | None

    def __post_init__(self) -> None:
        if self.submitted_at is None:
            return
        try:
            submitted = datetime.fromisoformat(self.submitted_at)
        except ValueError as error:
            raise CanaryStateCorruptError("invalid order submission timestamp") from error
        if submitted.tzinfo is None:
            raise CanaryStateCorruptError("order submission timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CanaryState:
    market_date: str
    nonce: str
    account_fingerprint: str
    executable_sha256: str
    mode: StateMode
    owned_symbol: str | None
    max_owned_quantity: int
    round_trips: int
    entry_attempts: int
    exit_attempts: int
    intent: OrderIntent | None
    known_order: KnownOrder | None = None
    confirmed_entry_price_usd: Decimal | None = None
    cooldown_until: str | None = None
    get_calls_used: int = 0
    last_exit_limit_price_usd: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.market_date or not self.nonce: raise CanaryStateCorruptError("market date and nonce are required")
        if self.max_owned_quantity not in (0, CANARY_POLICY.quantity): raise CanaryStateCorruptError("owned quantity exceeds fixed canary quantity")
        if self.owned_symbol is None and self.max_owned_quantity != 0: raise CanaryStateCorruptError("owned quantity requires owned symbol")
        if self.owned_symbol is not None and self.max_owned_quantity != CANARY_POLICY.quantity: raise CanaryStateCorruptError("owned symbol requires one share")
        if min(self.round_trips, self.entry_attempts, self.exit_attempts) < 0: raise CanaryStateCorruptError("attempt counters must be non-negative")
        if not 0 <= self.get_calls_used <= CANARY_POLICY.daily_get_budget: raise CanaryStateCorruptError("GET usage exceeds daily budget")
        if self.last_exit_limit_price_usd is not None and self.last_exit_limit_price_usd <= 0: raise CanaryStateCorruptError("last exit limit price must be positive")
        if self.cooldown_until is not None:
            try:
                cooldown = datetime.fromisoformat(self.cooldown_until)
            except ValueError as error:
                raise CanaryStateCorruptError("invalid cooldown timestamp") from error
            if cooldown.tzinfo is None: raise CanaryStateCorruptError("cooldown timestamp must be timezone-aware")
        if self.intent is not None and self.known_order is not None: raise CanaryStateCorruptError("intent and known order cannot coexist")
        if self.known_order is not None and self.known_order.side is OrderSide.SELL and self.known_order.symbol != self.owned_symbol: raise CanaryStateCorruptError("known sell must match owned symbol")
        match self.mode:
            case StateMode.ARMED:
                return
            case StateMode.EXIT_ONLY:
                if self.owned_symbol is None: raise CanaryStateCorruptError("exit-only requires an owned symbol")
            case StateMode.MANUAL_RECONCILIATION_REQUIRED:
                return
            case StateMode.COMPLETED:
                if self.owned_symbol is not None or self.intent is not None or self.known_order is not None: raise CanaryStateCorruptError("completed state cannot retain exposure")
            case unreachable:
                assert_never(unreachable)

    def with_owned_position(self, symbol: str, quantity: int) -> CanaryState:
        if quantity != CANARY_POLICY.quantity: raise CanaryStateTransitionError("only one confirmed share can be owned")
        return replace(self, owned_symbol=symbol, max_owned_quantity=quantity)

    def expire_arm(self) -> CanaryState:
        if self.intent is not None or self.known_order is not None: raise CanaryStateTransitionError("pending known order blocks arm expiry")
        if self.owned_symbol is None: raise CanaryStateTransitionError("cannot create exit-only without an owned position")
        return replace(self, mode=StateMode.EXIT_ONLY, intent=None)

    def record_intent(self, intent: OrderIntent) -> CanaryState:
        if self.intent is not None: raise CanaryStateTransitionError("existing intent requires reconciliation")
        if self.known_order is not None: raise CanaryStateTransitionError("known order requires reconciliation")
        match self.mode:
            case StateMode.ARMED:
                return self._record_armed_intent(intent)
            case StateMode.EXIT_ONLY:
                return self._record_exit_only_intent(intent)
            case StateMode.MANUAL_RECONCILIATION_REQUIRED:
                raise CanaryStateTransitionError("manual reconciliation is terminal")
            case StateMode.COMPLETED:
                raise CanaryStateTransitionError("completed state is terminal")
            case unreachable:
                assert_never(unreachable)

    def for_next_session(self, market_date: str) -> CanaryState:
        if market_date <= self.market_date: raise CanaryStateTransitionError("next market date must advance")
        match self.mode:
            case StateMode.ARMED:
                return replace(self, market_date=market_date, exit_attempts=0, get_calls_used=0, last_exit_limit_price_usd=None)
            case StateMode.EXIT_ONLY:
                return replace(self, market_date=market_date, exit_attempts=0, intent=None, get_calls_used=0, last_exit_limit_price_usd=None)
            case StateMode.MANUAL_RECONCILIATION_REQUIRED:
                return replace(self, market_date=market_date, intent=None, get_calls_used=0, last_exit_limit_price_usd=None)
            case StateMode.COMPLETED:
                return replace(self, market_date=market_date, intent=None, get_calls_used=0, last_exit_limit_price_usd=None)
            case unreachable:
                assert_never(unreachable)

    def _record_armed_intent(self, intent: OrderIntent) -> CanaryState:
        match intent.side:
            case OrderSide.BUY:
                if self.round_trips >= CANARY_POLICY.maximum_round_trips: raise CanaryStateTransitionError("round trip limit reached")
                if self.owned_symbol is not None: raise CanaryStateTransitionError("owned position blocks new entry")
                if intent.limit_price_usd > CANARY_POLICY.entry_limit_price_usd: raise CanaryStateTransitionError("entry price exceeds fixed cap")
                if self.entry_attempts >= CANARY_POLICY.maximum_entry_attempts: raise CanaryStateTransitionError("entry attempt limit reached")
                return replace(self, entry_attempts=self.entry_attempts + 1, intent=intent)
            case OrderSide.SELL:
                if intent.symbol != self.owned_symbol: raise CanaryStateTransitionError("sell must match owned symbol")
                if self.exit_attempts >= CANARY_POLICY.maximum_exit_attempts: raise CanaryStateTransitionError("exit attempt limit reached")
                return replace(self, exit_attempts=self.exit_attempts + 1, intent=intent, last_exit_limit_price_usd=intent.limit_price_usd)
            case unreachable:
                assert_never(unreachable)

    def _record_exit_only_intent(self, intent: OrderIntent) -> CanaryState:
        match intent.side:
            case OrderSide.BUY:
                raise CanaryStateTransitionError("exit-only never permits buys")
            case OrderSide.SELL:
                if intent.symbol != self.owned_symbol: raise CanaryStateTransitionError("exit-only sell must match owned symbol")
                if self.exit_attempts >= CANARY_POLICY.maximum_exit_attempts: raise CanaryStateTransitionError("exit attempt limit reached")
                return replace(self, exit_attempts=self.exit_attempts + 1, intent=intent, last_exit_limit_price_usd=intent.limit_price_usd)
            case unreachable:
                assert_never(unreachable)

    def complete_intent(self, order_id: str, submitted_at: datetime) -> CanaryState:
        if self.intent is None or not order_id: raise CanaryStateTransitionError("exact order ID requires a pending intent")
        if submitted_at.tzinfo is None: raise CanaryStateTransitionError("order submission timestamp must be timezone-aware")
        known = KnownOrder(order_id, self.intent.symbol, self.intent.side, self.intent.quantity, self.intent.limit_price_usd, submitted_at.isoformat())
        return replace(self, intent=None, known_order=known)

    def with_known_order_submitted_at(self, submitted_at: datetime) -> CanaryState:
        if self.known_order is None: raise CanaryStateTransitionError("known order is required")
        if submitted_at.tzinfo is None: raise CanaryStateTransitionError("order submission timestamp must be timezone-aware")
        return replace(
            self,
            known_order=replace(
                self.known_order,
                submitted_at=submitted_at.isoformat(),
            ),
        )

    def clear_completed_order(self, order_id: str) -> CanaryState:
        if self.known_order is None or self.known_order.order_id != order_id: raise CanaryStateTransitionError("only the exact known order can clear")
        return replace(self, known_order=None)

    def require_manual_reconciliation(self) -> CanaryState:
        return replace(self, mode=StateMode.MANUAL_RECONCILIATION_REQUIRED)

    def confirm_owned_position(self, symbol: str, quantity: int, entry_price: Decimal) -> CanaryState:
        if self.known_order is None or self.known_order.side is not OrderSide.BUY: raise CanaryStateTransitionError("exact known buy required")
        if (symbol, quantity) != (self.known_order.symbol, self.known_order.quantity) or entry_price <= 0: raise CanaryStateTransitionError("confirmed position does not match known buy")
        return replace(self, owned_symbol=symbol, max_owned_quantity=quantity, confirmed_entry_price_usd=entry_price, known_order=None)

    def confirm_exit(self, order_id: str) -> CanaryState:
        if self.known_order is None or self.known_order.order_id != order_id or self.known_order.side is not OrderSide.SELL: raise CanaryStateTransitionError("exact known sell required")
        next_mode = StateMode.COMPLETED if self.mode is StateMode.EXIT_ONLY else self.mode
        return replace(self, mode=next_mode, owned_symbol=None, max_owned_quantity=0, confirmed_entry_price_usd=None, known_order=None, round_trips=self.round_trips + 1, exit_attempts=0, last_exit_limit_price_usd=None)

    def cancel_known_order(self, order_id: str) -> CanaryState: return self.clear_completed_order(order_id)

    def with_cooldown_until(self, value: str) -> CanaryState:
        return replace(self, cooldown_until=value)

    def with_get_calls_used(self, value: int) -> CanaryState:
        return replace(self, get_calls_used=value)


class CanaryStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save(self, state: CanaryState) -> None:
        payload = _serialize(state)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self._path.parent, delete=False) as output:
                temporary_path = Path(output.name)
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, self._path)
        except OSError as error:
            raise CanaryStateCorruptError("durable state write failed") from error

    def load(self, *, expected_nonce: str) -> CanaryState:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError as error:
            raise CanaryStateCorruptError("state read failed") from error
        state = _parse(raw)
        if state.nonce != expected_nonce:
            raise CanaryStateCorruptError("state nonce does not match arm")
        return state


def _serialize(state: CanaryState) -> str:
    from .live_canary_state_codec import serialize_state

    return serialize_state(state)


def _parse(raw: str) -> CanaryState:
    from .live_canary_state_codec import parse_state

    return parse_state(raw)
