from __future__ import annotations

import json
from decimal import Decimal
from typing import Mapping, TypeGuard

from .live_canary_policy import OrderSide
from .live_canary_state import (
    CanaryState,
    CanaryStateCorruptError,
    JsonValue,
    KnownOrder,
    OrderIntent,
    StateMode,
)


def serialize_state(state: CanaryState) -> str:
    intent = _intent_payload(state.intent)
    payload = {
        "schema_version": 1,
        "market_date": state.market_date,
        "nonce": state.nonce,
        "account_fingerprint": state.account_fingerprint,
        "executable_sha256": state.executable_sha256,
        "mode": state.mode.value,
        "owned_symbol": state.owned_symbol,
        "max_owned_quantity": state.max_owned_quantity,
        "round_trips": state.round_trips,
        "entry_attempts": state.entry_attempts,
        "exit_attempts": state.exit_attempts,
        "intent": intent,
        "known_order": _order_payload(state.known_order),
        "confirmed_entry_price_usd": (
            str(state.confirmed_entry_price_usd)
            if state.confirmed_entry_price_usd
            else None
        ),
        "cooldown_until": state.cooldown_until,
        "get_calls_used": state.get_calls_used,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def parse_state(raw: str) -> CanaryState:
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CanaryStateCorruptError("invalid JSON") from error
    if not _json_object(decoded):
        raise CanaryStateCorruptError("state root must be an object")
    prohibited = {"access_token", "app_key", "app_secret", "account_number"}
    if prohibited.intersection(decoded):
        raise CanaryStateCorruptError("state contains prohibited secret field")
    if decoded.get("schema_version") != 1:
        raise CanaryStateCorruptError("unsupported schema version")
    return CanaryState(
        market_date=_text(decoded, "market_date"),
        nonce=_text(decoded, "nonce"),
        account_fingerprint=_text(decoded, "account_fingerprint"),
        executable_sha256=_text(decoded, "executable_sha256"),
        mode=_mode(_text(decoded, "mode")),
        owned_symbol=_optional_text(decoded, "owned_symbol"),
        max_owned_quantity=_integer(decoded, "max_owned_quantity"),
        round_trips=_integer(decoded, "round_trips"),
        entry_attempts=_integer(decoded, "entry_attempts"),
        exit_attempts=_integer(decoded, "exit_attempts"),
        intent=_intent(decoded.get("intent")),
        known_order=_known_order(decoded.get("known_order")),
        confirmed_entry_price_usd=_optional_decimal(
            decoded.get("confirmed_entry_price_usd")
        ),
        cooldown_until=_optional_text(decoded, "cooldown_until"),
        get_calls_used=_optional_integer(decoded, "get_calls_used", 0),
    )


def _intent_payload(intent: OrderIntent | None) -> dict[str, str | int] | None:
    if intent is None:
        return None
    return {
        "symbol": intent.symbol,
        "side": intent.side.value,
        "quantity": intent.quantity,
        "limit_price_usd": str(intent.limit_price_usd),
    }


def _order_payload(order: KnownOrder | None) -> dict[str, str | int] | None:
    if order is None:
        return None
    return {
        "order_id": order.order_id,
        "symbol": order.symbol,
        "side": order.side.value,
        "quantity": order.quantity,
        "limit_price_usd": str(order.limit_price_usd),
    }


def _text(raw: Mapping[str, JsonValue], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value:
        raise CanaryStateCorruptError(f"invalid {field}")
    return value


def _optional_text(raw: Mapping[str, JsonValue], field: str) -> str | None:
    value = raw.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise CanaryStateCorruptError(f"invalid {field}")
    return value


def _integer(raw: Mapping[str, JsonValue], field: str) -> int:
    value = raw.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise CanaryStateCorruptError(f"invalid {field}")
    return value


def _optional_integer(raw: Mapping[str, JsonValue], field: str, default: int) -> int:
    return default if field not in raw else _integer(raw, field)


def _mode(value: str) -> StateMode:
    try:
        return StateMode(value)
    except ValueError as error:
        raise CanaryStateCorruptError("invalid mode") from error


def _intent(value: JsonValue) -> OrderIntent | None:
    if value is None:
        return None
    if not _json_object(value):
        raise CanaryStateCorruptError("invalid intent")
    try:
        side = OrderSide(_text(value, "side"))
    except ValueError as error:
        raise CanaryStateCorruptError("invalid intent side") from error
    return OrderIntent(
        symbol=_text(value, "symbol"),
        side=side,
        quantity=_integer(value, "quantity"),
        limit_price_usd=_decimal(_text(value, "limit_price_usd")),
    )


def _known_order(value: JsonValue) -> KnownOrder | None:
    if value is None:
        return None
    if not _json_object(value):
        raise CanaryStateCorruptError("invalid known order")
    try:
        side = OrderSide(_text(value, "side"))
    except ValueError as error:
        raise CanaryStateCorruptError("invalid known order side") from error
    return KnownOrder(
        _text(value, "order_id"),
        _text(value, "symbol"),
        side,
        _integer(value, "quantity"),
        _decimal(_text(value, "limit_price_usd")),
    )


def _optional_decimal(value: JsonValue) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CanaryStateCorruptError("invalid confirmed entry price")
    return _decimal(value)


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except ArithmeticError as error:
        raise CanaryStateCorruptError("invalid decimal") from error


def _json_object(value: JsonValue) -> TypeGuard[Mapping[str, JsonValue]]:
    return isinstance(value, dict)
