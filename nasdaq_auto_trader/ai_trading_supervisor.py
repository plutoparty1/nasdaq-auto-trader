from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum, unique

from .ai_quant_lab.types import JsonValue


@unique
class SupervisorAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True, slots=True)
class SupervisorDecisionError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class SupervisorDecision:
    symbol: str
    action: SupervisorAction
    confidence: float
    target_position_pct: float
    signal_timestamp: datetime
    model_version: str
    market_regime: str
    reason_codes: tuple[str, ...]
    risk_flags: tuple[str, ...]
    summary: str


REQUIRED_FIELDS = {
    "symbol",
    "action",
    "confidence",
    "target_position_pct",
    "signal_timestamp",
    "model_version",
    "market_regime",
    "reason_codes",
    "risk_flags",
    "summary",
}


def parse_supervisor_decision(
    raw_response: str,
    now: datetime,
    max_age_seconds: int,
) -> SupervisorDecision:
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise SupervisorDecisionError("supervisor_invalid_json") from exc
    if not isinstance(payload, dict):
        raise SupervisorDecisionError("supervisor_root_must_be_object")
    unknown = set(payload) - REQUIRED_FIELDS
    missing = REQUIRED_FIELDS - set(payload)
    if unknown:
        raise SupervisorDecisionError("supervisor_unknown_fields")
    if missing:
        raise SupervisorDecisionError("supervisor_missing_fields")

    symbol = _required_text(payload["symbol"], "symbol").upper()
    if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol) is None:
        raise SupervisorDecisionError("supervisor_symbol_invalid")
    try:
        action = SupervisorAction(_required_text(payload["action"], "action"))
    except ValueError as exc:
        raise SupervisorDecisionError("supervisor_action_invalid") from exc
    confidence = _bounded_number(payload["confidence"], "confidence")
    target = _bounded_number(payload["target_position_pct"], "target_position_pct")
    signal_timestamp = _timestamp(payload["signal_timestamp"])
    normalized_now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    age = (normalized_now - signal_timestamp).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise SupervisorDecisionError("supervisor_signal_stale")
    return SupervisorDecision(
        symbol=symbol,
        action=action,
        confidence=confidence,
        target_position_pct=target,
        signal_timestamp=signal_timestamp,
        model_version=_required_text(payload["model_version"], "model_version"),
        market_regime=_required_text(payload["market_regime"], "market_regime"),
        reason_codes=_text_tuple(payload["reason_codes"], "reason_codes"),
        risk_flags=_text_tuple(payload["risk_flags"], "risk_flags", allow_empty=True),
        summary=_required_text(payload["summary"], "summary"),
    )


def _required_text(value: JsonValue, field: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise SupervisorDecisionError(f"supervisor_{field}_invalid")


def _bounded_number(value: JsonValue, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SupervisorDecisionError(f"supervisor_{field}_invalid")
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise SupervisorDecisionError(f"supervisor_{field}_invalid")
    return parsed


def _timestamp(value: JsonValue) -> datetime:
    text = _required_text(value, "signal_timestamp")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SupervisorDecisionError("supervisor_signal_timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise SupervisorDecisionError("supervisor_signal_timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def _text_tuple(
    value: JsonValue,
    field: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise SupervisorDecisionError(f"supervisor_{field}_invalid")
    parsed = tuple(item.strip() for item in value)
    if not parsed and not allow_empty:
        raise SupervisorDecisionError(f"supervisor_{field}_invalid")
    return parsed
