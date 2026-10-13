from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from .models import Action

EntryPolicyName = Literal["A", "B", "C"]


@dataclass(frozen=True, slots=True)
class EntryPolicyInputError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def parse_policy(value: str) -> EntryPolicyName:
    if value not in ("A", "B", "C"):
        raise EntryPolicyInputError("entry policy must be A, B, or C")
    return value


def completed_timestamp(value: str) -> datetime | None:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return None
    return timestamp.astimezone(timezone.utc)


def market_session(value: str) -> str:
    timestamp = completed_timestamp(value)
    if timestamp is None:
        raise EntryPolicyInputError("session timestamp must have an explicit timezone")
    return timestamp.astimezone(ZoneInfo("America/New_York")).date().isoformat()


@dataclass(frozen=True, slots=True)
class EntryDecisionRecord:
    symbol: str
    policy: EntryPolicyName
    evaluation_timestamp: str
    completed_bar_id: str
    data_fingerprint: str
    buy_score: int | None
    sell_score: int | None
    base_action: Action
    final_action: Action
    forced: bool
    no_trade: bool
    reason: str
    entry_condition_met: bool
    duplicate_general_evaluation: bool
    protective_evaluation: bool
    indicator_price: float | None
    protective_mark: float | None
    stress_risk_distance: float | None
