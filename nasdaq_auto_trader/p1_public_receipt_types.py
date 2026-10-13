from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol, TypedDict
from zoneinfo import ZoneInfo

from .research_public_bars import JsonValue
from .research_public_transport import PublicDataError, PublicRequestBounds

Clock = Callable[[], datetime]


class PublicFetcher(Protocol):
    def __call__(self, url: str, *, bounds: PublicRequestBounds) -> bytes: ...


class RawReceipt(TypedDict):
    source: str
    request_started_at: str
    received_at: str | None
    raw_file: str
    raw_sha256: str | None


class StockReceipt(RawReceipt):
    symbol: str
    missing_dates: list[str]
    events: dict[str, JsonValue]


class Receipt(TypedDict):
    schema_version: int
    kind: str
    request_started_at: str
    created_at: str
    requested_start: str
    requested_end: str
    calendar_sha256: str
    files: dict[str, str]
    stocks: list[StockReceipt]
    fx: RawReceipt
    failures: list[str]


@dataclass(frozen=True, slots=True)
class CalendarSnapshot:
    sha256: str
    sessions: dict[str, datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def clock_utc(clock: Clock) -> datetime:
    instant = clock()
    if instant.utcoffset() is None:
        raise PublicDataError("public_clock_timezone_required")
    return instant.astimezone(UTC)


def load_calendar(path: Path) -> CalendarSnapshot:
    raw = path.read_bytes()
    try:
        rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if rows.fieldnames != ["session_date", "open_at", "close_at"]:
            raise PublicDataError("public_calendar_columns_invalid")
        sessions: dict[str, datetime] = {}
        for row in rows:
            if set(row) != {"session_date", "open_at", "close_at"}:
                raise PublicDataError("public_calendar_columns_invalid")
            day = date.fromisoformat(row["session_date"])
            opening = datetime.fromisoformat(row["open_at"])
            close = datetime.fromisoformat(row["close_at"])
            if (
                day.isoformat() != row["session_date"]
                or day.isoformat() in sessions
                or day.weekday() >= 5
                or opening.utcoffset() is None
                or close.utcoffset() is None
                or opening >= close
                or opening.astimezone(ZoneInfo("America/New_York")).date() != day
                or close.astimezone(ZoneInfo("America/New_York")).date() != day
            ):
                raise PublicDataError("public_calendar_session_invalid")
            sessions[day.isoformat()] = close.astimezone(UTC)
        if not sessions:
            raise PublicDataError("public_calendar_empty")
        return CalendarSnapshot(hashlib.sha256(raw).hexdigest(), sessions)
    except (ValueError, TypeError, UnicodeError, csv.Error):
        raise PublicDataError("public_calendar_payload_invalid") from None
