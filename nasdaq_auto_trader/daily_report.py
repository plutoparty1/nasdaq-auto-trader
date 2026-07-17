from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .ai_quant_lab.operator_gui_presenter import human_reason
from .ai_quant_lab.types import JsonObject, JsonValue
from .app_types import PortfolioSnapshot
from .config_settings import TradingSettings
from .market_hours import EASTERN, latest_completed_market_date
from .runtime_journal import RuntimeEvent, RuntimeEventType, RuntimeJournalWriter
from .daily_report_markdown import render_daily_report
from .daily_report_models import AuditSummary, DailyReportResult


class DailyReportError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class DailyReportService:
    def __init__(
        self,
        report_root: Path,
        audit_path: Path,
        runtime_journal: RuntimeJournalWriter | None = None,
    ) -> None:
        self.report_root = report_root
        self.audit_path = audit_path
        self.runtime_journal = runtime_journal

    def target_market_date(self, now: datetime) -> str:
        return latest_completed_market_date(_as_utc(now))

    def is_due(self, now: datetime, settings: TradingSettings) -> bool:
        if not settings.daily_report_enabled:
            return False
        local_now = _as_local(now)
        cutoff = local_now.replace(
            hour=settings.daily_report_hour,
            minute=settings.daily_report_minute,
            second=0,
            microsecond=0,
        )
        market_date = self.target_market_date(now)
        return bool(
            market_date
            and local_now >= cutoff
            and not self._report_path(market_date).exists()
        )

    def latest_path(self) -> Path | None:
        paths = sorted(
            path
            for path in self.report_root.glob("daily-*.md")
            if _date_from_report_path(path) is not None
        )
        return paths[-1] if paths else None

    def generate(
        self,
        now: datetime,
        settings: TradingSettings,
        snapshot: PortfolioSnapshot | None,
    ) -> DailyReportResult:
        market_date = self.target_market_date(now)
        if not market_date:
            raise DailyReportError("completed_market_date_unavailable")
        summary = _summarize_audit(self.audit_path, market_date)
        path = self._report_path(market_date)
        self.report_root.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".md.tmp")
        temporary.write_text(
            render_daily_report(market_date, now, summary, snapshot),
            encoding="utf-8",
        )
        os.replace(temporary, path)
        self._remove_expired(now, settings.daily_report_retention_days)
        if self.runtime_journal is not None:
            self.runtime_journal.append(
                RuntimeEvent(
                    RuntimeEventType.DAILY_REPORT_GENERATED,
                    now,
                    reason="completed",
                )
            )
        return DailyReportResult(
            market_date,
            path,
            summary.cycle_count,
            summary.submitted_orders,
            summary.blocked_orders,
            summary.skipped_lines,
        )

    def _report_path(self, market_date: str) -> Path:
        return self.report_root / f"daily-{market_date}.md"

    def _remove_expired(self, now: datetime, retention_days: int) -> None:
        cutoff = now.date() - timedelta(days=retention_days)
        for path in self.report_root.glob("daily-*.md"):
            report_date = _date_from_report_path(path)
            if report_date is not None and report_date < cutoff:
                path.unlink(missing_ok=True)


def _summarize_audit(path: Path, market_date: str) -> AuditSummary:
    cycles = transitions = generated = accepted = submitted = blocked = skipped = 0
    states: set[str] = set()
    reasons: list[str] = []
    if not path.exists():
        return AuditSummary(0, 0, 0, 0, 0, 0, (), (), 0)
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value: JsonValue = json.loads(line)
            event = _audit_event(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            skipped += 1
            continue
        if event is None:
            skipped += 1
            continue
        timestamp, event_type, payload = event
        event_market_date = timestamp.astimezone(EASTERN).date().isoformat()
        if event_type == "learning_completed":
            event_market_date = _text(payload.get("market_date")) or event_market_date
        if event_market_date != market_date:
            continue
        include_reason = False
        if event_type == "trading_cycle_completed":
            cycles += 1
        elif event_type == "operating_transition":
            transitions += 1
            include_reason = True
            state = _text(payload.get("state"))
            if state:
                states.add(state)
        elif event_type == "learning_completed":
            include_reason = True
            generated += _nonnegative_int(payload.get("generated_candidates"))
            accepted += _nonnegative_int(payload.get("accepted_candidates"))
        elif event_type == "automatic_order_submitted":
            submitted += 1
        elif event_type == "automatic_order_blocked":
            blocked += 1
            include_reason = True
        reason = _text(payload.get("reason")) if include_reason else ""
        if reason:
            label = human_reason(reason)
            if label not in reasons:
                reasons.append(label)
    return AuditSummary(
        cycles,
        transitions,
        generated,
        accepted,
        submitted,
        blocked,
        tuple(sorted(states)),
        tuple(reasons),
        skipped,
    )


def _audit_event(value: JsonValue) -> tuple[datetime, str, JsonObject] | None:
    if not isinstance(value, dict):
        return None
    timestamp_text = _text(value.get("timestamp"))
    event_type = _text(value.get("event_type"))
    payload = value.get("payload")
    if not timestamp_text or not event_type or not isinstance(payload, dict):
        return None
    timestamp = datetime.fromisoformat(timestamp_text)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp, event_type, payload


def _as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _as_local(value: datetime) -> datetime:
    return value.astimezone()


def _text(value: JsonValue | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def _nonnegative_int(value: JsonValue | None) -> int:
    valid = isinstance(value, int) and not isinstance(value, bool) and value > 0
    return value if valid else 0


def _date_from_report_path(path: Path) -> date | None:
    try:
        return date.fromisoformat(path.stem.removeprefix("daily-"))
    except ValueError:
        return None
