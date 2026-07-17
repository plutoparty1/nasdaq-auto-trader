from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum, unique
from pathlib import Path
from typing import Protocol

from .ai_quant_lab.audit_logger import AuditEvent, AuditLogger


@unique
class RuntimeEventType(StrEnum):
    UNATTENDED_STARTED = "unattended_started"
    OPERATING_TRANSITION = "operating_transition"
    LEARNING_COMPLETED = "learning_completed"
    TRADING_CYCLE_COMPLETED = "trading_cycle_completed"
    PORTFOLIO_SNAPSHOT = "portfolio_snapshot"
    DAILY_REPORT_GENERATED = "daily_report_generated"


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    event_type: RuntimeEventType
    timestamp: datetime
    state: str = ""
    reason: str = ""
    generated_candidates: int = 0
    accepted_candidates: int = 0
    submitted_orders: int = 0
    result_count: int = 0
    cash: float | None = None
    equity: float | None = None
    buying_power: float | None = None
    market_date: str = ""


class RuntimeJournalWriter(Protocol):
    def append(self, event: RuntimeEvent) -> bool: ...


class RuntimeJournal:
    def __init__(self, path: Path) -> None:
        self._audit = AuditLogger(path)

    def append(self, event: RuntimeEvent) -> bool:
        payload = {
            "state": event.state,
            "reason": event.reason,
            "generated_candidates": event.generated_candidates,
            "accepted_candidates": event.accepted_candidates,
            "submitted_orders": event.submitted_orders,
            "result_count": event.result_count,
            "cash": event.cash,
            "equity": event.equity,
            "buying_power": event.buying_power,
            "market_date": event.market_date,
        }
        return self._audit.append(
            AuditEvent(
                event.event_type.value,
                timestamp=event.timestamp.astimezone(timezone.utc).isoformat(),
                payload=payload,
            )
        )


class NullRuntimeJournal:
    def append(self, event: RuntimeEvent) -> bool:
        del event
        return True
