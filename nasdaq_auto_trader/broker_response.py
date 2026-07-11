from __future__ import annotations

from typing import Final

from nasdaq_auto_trader.ai_quant_lab.types import JsonObject, JsonValue


SUCCESS_BROKER_STATUSES: Final[frozenset[str]] = frozenset(
    {"accepted", "filled", "new", "pending_new", "submitted", "fake_submitted"}
)


def broker_response_status(response: JsonObject) -> str:
    status = _string(response.get("status")).lower()
    if status:
        return "submitted" if status in SUCCESS_BROKER_STATUSES else status
    if response.get("rt_cd") == "0" or _string(response.get("id")):
        return "submitted"
    return "order_response_missing_status"


def broker_response_submitted(response: JsonObject) -> bool:
    return broker_response_status(response) == "submitted"


def _string(value: JsonValue) -> str:
    return value.strip() if isinstance(value, str) else ""
