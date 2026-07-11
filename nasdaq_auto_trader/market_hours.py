"""US equity regular-market session checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import TypedDict
from zoneinfo import ZoneInfo


EASTERN = ZoneInfo("America/New_York")
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)


class MarketSessionDict(TypedDict):
    is_open: bool
    reason: str
    market_time: str
    opens_at: str
    closes_at: str
    timezone: str


@dataclass(frozen=True, slots=True)
class MarketSession:
    """Result of checking the US regular equity trading session."""

    is_open: bool
    reason: str
    market_time: str
    opens_at: str
    closes_at: str
    timezone: str = "America/New_York"

    def to_dict(self) -> MarketSessionDict:
        """Return JSON-safe session details."""

        return {
            "is_open": self.is_open,
            "reason": self.reason,
            "market_time": self.market_time,
            "opens_at": self.opens_at,
            "closes_at": self.closes_at,
            "timezone": self.timezone,
        }


def regular_market_session(now: datetime | None = None) -> MarketSession:
    """Return whether the US equity regular session is open at ``now``."""

    market_now = _to_eastern(now or datetime.now(timezone.utc))
    today = market_now.date()
    close_time = _early_close_time(today) or REGULAR_CLOSE
    opens_at = datetime.combine(today, REGULAR_OPEN, tzinfo=EASTERN)
    closes_at = datetime.combine(today, close_time, tzinfo=EASTERN)

    if market_now.weekday() >= 5:
        return _session(False, "weekend", market_now, opens_at, closes_at)
    if today in _market_holidays(today.year):
        return _session(False, "market_holiday", market_now, opens_at, closes_at)
    if market_now < opens_at:
        return _session(False, "before_regular_open", market_now, opens_at, closes_at)
    if market_now >= closes_at:
        return _session(False, "after_regular_close", market_now, opens_at, closes_at)
    return _session(True, "regular_market_open", market_now, opens_at, closes_at)


def _session(
    is_open: bool,
    reason: str,
    market_now: datetime,
    opens_at: datetime,
    closes_at: datetime,
) -> MarketSession:
    return MarketSession(
        is_open=is_open,
        reason=reason,
        market_time=market_now.isoformat(),
        opens_at=opens_at.isoformat(),
        closes_at=closes_at.isoformat(),
    )


def _to_eastern(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(EASTERN)


def _market_holidays(year: int) -> set[date]:
    holidays = {
        _observed_fixed_holiday(year, 1, 1),
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
        _easter_sunday(year) - timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed_fixed_holiday(year, 6, 19),  # Juneteenth
        _observed_fixed_holiday(year, 7, 4),  # Independence Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving Day
        _observed_fixed_holiday(year, 12, 25),  # Christmas Day
    }
    next_new_year = _observed_fixed_holiday(year + 1, 1, 1)
    if next_new_year.year == year:
        holidays.add(next_new_year)
    return holidays


def _early_close_time(value: date) -> time | None:
    if value in _market_holidays(value.year) or value.weekday() >= 5:
        return None

    thanksgiving = _nth_weekday(value.year, 11, 3, 4)
    if value == thanksgiving + timedelta(days=1):
        return EARLY_CLOSE

    if value.month == 7 and value.day == 3:
        return EARLY_CLOSE

    if value.month == 12 and value.day == 24:
        return EARLY_CLOSE

    return None


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    current = date(year, month, 1)
    offset = (weekday - current.weekday()) % 7
    return current + timedelta(days=offset + 7 * (nth - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    current = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    current -= timedelta(days=1)
    offset = (current.weekday() - weekday) % 7
    return current - timedelta(days=offset)


def _easter_sunday(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)
