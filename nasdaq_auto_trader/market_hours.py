from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import TypedDict
from zoneinfo import ZoneInfo

import pandas_market_calendars as market_calendars


EASTERN = ZoneInfo("America/New_York")
NASDAQ = market_calendars.get_calendar("NASDAQ")


class MarketSessionDict(TypedDict):
    is_open: bool
    reason: str
    market_time: str
    opens_at: str
    closes_at: str
    timezone: str


@dataclass(frozen=True, slots=True)
class MarketTimeError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class MarketSession:
    is_open: bool
    reason: str
    market_time: str
    opens_at: str
    closes_at: str
    timezone: str = "America/New_York"

    def to_dict(self) -> MarketSessionDict:
        return {
            "is_open": self.is_open,
            "reason": self.reason,
            "market_time": self.market_time,
            "opens_at": self.opens_at,
            "closes_at": self.closes_at,
            "timezone": self.timezone,
        }


def regular_market_session(now: datetime | None = None) -> MarketSession:
    market_now = _to_eastern(now or datetime.now(timezone.utc))
    schedule = NASDAQ.schedule(start_date=market_now.date(), end_date=market_now.date())
    if schedule.empty:
        reason = "weekend" if market_now.weekday() >= 5 else "market_holiday"
        return MarketSession(False, reason, market_now.isoformat(), "", "")

    opens_at = schedule.iloc[0]["market_open"].to_pydatetime().astimezone(EASTERN)
    closes_at = schedule.iloc[0]["market_close"].to_pydatetime().astimezone(EASTERN)
    if market_now < opens_at:
        reason = "before_regular_open"
    elif market_now >= closes_at:
        reason = "after_regular_close"
    else:
        reason = "regular_market_open"
    return MarketSession(
        reason == "regular_market_open",
        reason,
        market_now.isoformat(),
        opens_at.isoformat(),
        closes_at.isoformat(),
    )


def authorization_market_date(now: datetime) -> date:
    if now.tzinfo is None:
        raise MarketTimeError("market_time_timezone_required")
    normalized = now.astimezone(timezone.utc)
    schedule = NASDAQ.schedule(
        start_date=normalized.date(),
        end_date=(normalized + timedelta(days=14)).date(),
    )
    upcoming = schedule[schedule["market_close"] > normalized]
    if upcoming.empty:
        raise MarketTimeError("market_calendar_unavailable")
    return upcoming.index[0].date()


def latest_completed_market_date(now: datetime) -> str:
    normalized = (
        now.replace(tzinfo=timezone.utc)
        if now.tzinfo is None
        else now.astimezone(timezone.utc)
    )
    schedule = NASDAQ.schedule(
        start_date=(normalized - timedelta(days=14)).date(),
        end_date=normalized.date(),
    )
    completed = schedule[schedule["market_close"] <= normalized]
    return "" if completed.empty else completed.index[-1].date().isoformat()


def _to_eastern(value: datetime) -> datetime:
    normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return normalized.astimezone(EASTERN)
