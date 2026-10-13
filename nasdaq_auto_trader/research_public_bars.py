"""Parse public daily bars without reading account or live application state."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import TypeAlias
from zoneinfo import ZoneInfo

from .research_public_transport import SYMBOLS, PublicDataError

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)
HOLIDAYS = frozenset(
    [
        "2024-09-02",
        "2024-11-28",
        "2024-12-25",
        "2025-01-01",
        "2025-01-09",
        "2025-01-20",
        "2025-02-17",
        "2025-04-18",
        "2025-05-26",
        "2025-06-19",
        "2025-07-04",
        "2025-09-01",
        "2025-11-27",
        "2025-12-25",
        "2026-01-01",
        "2026-01-19",
        "2026-02-16",
        "2026-04-03",
        "2026-05-25",
        "2026-06-19",
        "2026-07-03",
        "2026-09-07",
    ]
)
EARLY_CLOSES = frozenset(
    ["2024-11-29", "2024-12-24", "2025-07-03", "2025-11-28", "2025-12-24"]
)


@dataclass(frozen=True, slots=True)
class PublicBar:
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class DailyData:
    bars: tuple[PublicBar, ...]
    events: dict[str, JsonValue]
    adjusted_close: tuple[float | None, ...]
    missing_dates: tuple[str, ...]
    excluded_outside_period: int


def exchange_close(day: date) -> str:
    if not date(2024, 9, 1) <= day <= date(2026, 9, 28):
        raise PublicDataError("calendar_outside_verified_range")
    hour = 13 if day.isoformat() in EARLY_CLOSES else 16
    return (
        datetime.combine(day, time(hour), ZoneInfo("America/New_York"))
        .astimezone(timezone.utc)
        .isoformat()
    )


def expected_sessions(start: date, end: date) -> set[str]:
    return {
        (start + timedelta(days=i)).isoformat()
        for i in range((end - start).days + 1)
        if (start + timedelta(days=i)).weekday() < 5
        and (start + timedelta(days=i)).isoformat() not in HOLIDAYS
    }


def parse_yahoo_daily(
    content: bytes,
    symbol: str,
    start: date,
    end: date,
    *,
    sessions: Mapping[str, datetime] | None = None,
    completed_at: datetime | None = None,
) -> DailyData:
    if (sessions is None) != (completed_at is None):
        raise PublicDataError("public_calendar_cutoff_required")
    if completed_at is not None and completed_at.utcoffset() is None:
        raise PublicDataError("public_calendar_cutoff_invalid")
    try:
        document = json.loads(content)
        result = document["chart"]["result"][0]
        meta = result["meta"]
        if (
            document["chart"]["error"]
            or symbol not in SYMBOLS
            or meta["symbol"] != symbol
            or meta["currency"] != "USD"
            or meta["exchangeTimezoneName"] != "America/New_York"
        ):
            raise PublicDataError("public_bar_metadata_invalid")
        stamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        adjusted = result["indicators"].get(
            "adjclose", [{"adjclose": [None] * len(stamps)}]
        )[0]["adjclose"]
        if any(
            len(quote[key]) != len(stamps)
            for key in ("open", "high", "low", "close", "volume")
        ) or len(adjusted) != len(stamps):
            raise PublicDataError("public_bar_array_lengths")
        bars: list[PublicBar] = []
        adj_values: list[float | None] = []
        seen: set[str] = set()
        excluded = 0
        expected = (
            expected_sessions(start, end)
            if sessions is None
            else {
                day
                for day, close_at in sessions.items()
                if start.isoformat() <= day <= end.isoformat()
                and completed_at is not None
                and close_at <= completed_at
            }
        )
        for index, stamp in enumerate(stamps):
            if (
                isinstance(stamp, bool)
                or not isinstance(stamp, (int, float))
                or not math.isfinite(stamp)
            ):
                raise PublicDataError("public_bar_timestamp_invalid")
            day = (
                datetime.fromtimestamp(stamp, timezone.utc)
                .astimezone(ZoneInfo("America/New_York"))
                .date()
            )
            if not start <= day <= end:
                excluded += 1
                continue
            if sessions is not None:
                if day.isoformat() not in sessions:
                    raise PublicDataError("public_bar_duplicate_or_non_session")
                if (
                    completed_at is not None
                    and sessions[day.isoformat()] > completed_at
                ):
                    excluded += 1
                    continue
            if day.isoformat() in seen or day.isoformat() not in expected:
                raise PublicDataError("public_bar_duplicate_or_non_session")
            seen.add(day.isoformat())
            raw_values = [
                quote[key][index] for key in ("open", "high", "low", "close", "volume")
            ]
            if any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                for value in raw_values
            ):
                raise PublicDataError("public_bar_numeric_invalid")
            opening, high, low, close, volume = (float(value) for value in raw_values)
            if (
                not all(
                    math.isfinite(value) and value > 0
                    for value in (opening, high, low, close)
                )
                or not math.isfinite(volume)
                or volume < 0
                or low > min(opening, close)
                or high < max(opening, close)
                or low > high
            ):
                raise PublicDataError("public_bar_ohlcv_invalid")
            bars.append(
                PublicBar(
                    symbol,
                    exchange_close(day)
                    if sessions is None
                    else sessions[day.isoformat()].isoformat(),
                    opening,
                    high,
                    low,
                    close,
                    volume,
                )
            )
            adjusted_value = adjusted[index]
            if adjusted_value is not None and (
                isinstance(adjusted_value, bool)
                or not isinstance(adjusted_value, (float, int))
                or not math.isfinite(adjusted_value)
                or adjusted_value <= 0
            ):
                raise PublicDataError("public_adjclose_invalid")
            adj_values.append(adjusted_value)
        if not bars or [bar.timestamp for bar in bars] != sorted(
            bar.timestamp for bar in bars
        ):
            raise PublicDataError("public_bars_empty_or_unsorted")
        events = result.get("events", {})
        if sessions is not None:
            if not isinstance(events, dict):
                raise PublicDataError("public_bar_events_invalid")
            _ = json.dumps(events, allow_nan=False)
        return DailyData(
            tuple(bars),
            events,
            tuple(adj_values),
            tuple(sorted(expected - seen)),
            excluded,
        )
    except (ValueError, KeyError, IndexError, TypeError, OverflowError):
        raise PublicDataError("public_bar_payload_invalid") from None
