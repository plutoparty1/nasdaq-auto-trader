from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AuditSummary:
    cycle_count: int
    transition_count: int
    generated_candidates: int
    accepted_candidates: int
    submitted_orders: int
    blocked_orders: int
    states: tuple[str, ...]
    reasons: tuple[str, ...]
    skipped_lines: int


@dataclass(frozen=True, slots=True)
class DailyReportResult:
    market_date: str
    path: Path
    cycle_count: int
    submitted_orders: int
    blocked_orders: int
    skipped_audit_lines: int
