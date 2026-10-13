"""Account-linked fee evidence; planning assumptions never establish approval."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from .ai_quant_lab.types import JsonValue
from .live_authorization import broker_authorization_digest
from .production_runtime import ProductionRuntime


@dataclass(frozen=True, slots=True)
class FeeScheduleInput:
    commission_rate: float
    minimum_fee_usd: float
    tax_rate: float
    source: str
    source_kind: str = "manual_account_document"
    effective_from: str = ""
    effective_to: str = ""


@dataclass(frozen=True, slots=True)
class FeeSchedule:
    commission_rate: float
    minimum_fee_usd: float
    tax_rate: float
    source: str
    reviewed_at: str
    account_digest: str
    source_kind: str = "manual_account_document"
    effective_from: str = ""
    effective_to: str = ""
    verification_method: str = "manual_user_verified"


def parse_fee_schedule(payload: str, account_digest: str) -> FeeSchedule | None:
    try:
        value: JsonValue = json.loads(payload)
        if not isinstance(value, dict) or value.get("confirmed") is not True:
            return None
        if value.get("account_digest") != account_digest:
            return None
        commission, minimum, tax = (value.get("commission_rate"), value.get("minimum_fee_usd"), value.get("tax_rate"))
        if not isinstance(commission, int | float) or isinstance(commission, bool):
            return None
        if not isinstance(minimum, int | float) or isinstance(minimum, bool):
            return None
        if not isinstance(tax, int | float) or isinstance(tax, bool):
            return None
        if any(not math.isfinite(rate) or rate < 0 for rate in (commission, minimum, tax)):
            return None
        if commission >= 1 or tax >= 1:
            return None
        source, reviewed_at = value.get("source"), value.get("reviewed_at")
        if not isinstance(source, str) or not source.strip() or not isinstance(reviewed_at, str):
            return None
        reviewed = datetime.fromisoformat(reviewed_at)
        if reviewed.tzinfo is None:
            return None
        if value.get("source_kind") != "manual_account_document" or value.get("verification_method") != "manual_user_verified":