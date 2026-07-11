from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class ParsedSafetyState:
    market_date: str
    buy_count: int
    sell_count: int
    last_order_at: str
    daily_loss_breached: bool
    baseline_observed: bool


@dataclass(frozen=True, slots=True)
class SessionStateCodecError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def parse_safety_state(raw: dict) -> ParsedSafetyState:
    market_date = raw.get("market_date", "")
    buy_count = raw.get("buy_count", 0)
    sell_count = raw.get("sell_count", 0)
    last_order_at = raw.get("last_order_at", "")
    daily_loss_breached = raw.get("daily_loss_breached", False)
    baseline_observed = raw.get("baseline_observed", False)
    if not isinstance(market_date, str) or not isinstance(last_order_at, str):
        raise SessionStateCodecError("safety_text_field_invalid")
    if not _is_nonnegative_int(buy_count) or not _is_nonnegative_int(sell_count):
        raise SessionStateCodecError("safety_count_invalid")
    if not isinstance(daily_loss_breached, bool) or not isinstance(
        baseline_observed,
        bool,
    ):
        raise SessionStateCodecError("safety_boolean_invalid")
    parsed = ParsedSafetyState(
        market_date,
        buy_count,
        sell_count,
        last_order_at,
        daily_loss_breached,
        baseline_observed,
    )
    validate_safety_state(parsed)
    return parsed


def parse_claims(raw: dict) -> dict[str, str]:
    claims: dict[str, str] = {}
    for digest, status in raw.items():
        if not isinstance(digest, str) or not digest:
            raise SessionStateCodecError("claim_digest_invalid")
        if not isinstance(status, str):
            raise SessionStateCodecError("claim_status_invalid")
        claims[digest] = status
    return claims


def validate_safety_state(state: ParsedSafetyState) -> None:
    parsed_market_date(state.market_date)
    if not _is_nonnegative_int(state.buy_count) or not _is_nonnegative_int(
        state.sell_count
    ):
        raise SessionStateCodecError("safety_count_invalid")
    if not isinstance(state.daily_loss_breached, bool) or not isinstance(
        state.baseline_observed,
        bool,
    ):
        raise SessionStateCodecError("safety_boolean_invalid")
    if state.last_order_at:
        try:
            parsed = datetime.fromisoformat(state.last_order_at)
        except ValueError as exc:
            raise SessionStateCodecError("safety_timestamp_invalid") from exc
        if parsed.tzinfo is None:
            raise SessionStateCodecError("safety_timestamp_timezone_missing")


def parsed_market_date(value: str) -> date | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise SessionStateCodecError("safety_market_date_invalid") from exc
    if parsed.isoformat() != value:
        raise SessionStateCodecError("safety_market_date_invalid")
    return parsed


def required_market_date(value: str) -> date:
    parsed = parsed_market_date(value)
    if parsed is None:
        raise SessionStateCodecError("safety_market_date_missing")
    return parsed


def _is_nonnegative_int(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
