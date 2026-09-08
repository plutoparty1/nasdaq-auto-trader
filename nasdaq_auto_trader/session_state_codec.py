from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from typing import assert_never

from .models import PositionHighWater


@dataclass(frozen=True, slots=True)
class ParsedSafetyState:
    market_date: str
    buy_count: int
    sell_count: int
    last_order_at: str
    daily_loss_breached: bool
    baseline_observed: bool
    position_high_water: dict[str, PositionHighWater]
    closed_position_symbols: tuple[str, ...]
    position_state_versions: dict[str, int]


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
    position_high_water = _parse_position_high_water(
        raw.get("position_high_water", {})
    )
    closed_position_symbols = _parse_closed_position_symbols(
        raw.get("closed_position_symbols", [])
    )
    position_state_versions = _parse_position_state_versions(
        raw.get("position_state_versions", {})
    )
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
        position_high_water,
        closed_position_symbols,
        position_state_versions,
    )
    validate_safety_state(parsed)
    return parsed


def parse_claims(raw: dict) -> dict[str, tuple[str, str]]:
    claims: dict[str, tuple[str, str]] = {}
    for digest, value in raw.items():
        if not isinstance(digest, str) or not digest:
            raise SessionStateCodecError("claim_digest_invalid")
        if not isinstance(value, (str, dict)):
            raise SessionStateCodecError("claim_status_invalid")
        match_claim: str | dict = value
        match match_claim:
            case str(status):
                market_date = ""
            case dict() as fields:
                status = fields.get("status")
                market_date = fields.get("market_date")
            case unexpected:
                assert_never(unexpected)
        if not isinstance(status, str):
            raise SessionStateCodecError("claim_status_invalid")
        if not isinstance(market_date, str):
            raise SessionStateCodecError("claim_market_date_invalid")
        parsed_market_date(market_date)
        claims[digest] = status, market_date
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
    for symbol, value in state.position_high_water.items():
        if (
            not isinstance(symbol, str)
            or not symbol
            or not isinstance(value, PositionHighWater)
            or not isfinite(value.avg_entry_price)
            or value.avg_entry_price <= 0
            or not isfinite(value.high_water_price)
            or value.high_water_price <= 0
        ):
            raise SessionStateCodecError("position_high_water_invalid")
    if set(state.position_high_water) & set(state.closed_position_symbols):
        raise SessionStateCodecError("position_state_conflict")
    known_symbols = set(state.position_high_water) | set(state.closed_position_symbols)
    if not set(state.position_state_versions) <= known_symbols:
        raise SessionStateCodecError("position_state_versions_invalid")


def _parse_closed_position_symbols(raw: list) -> tuple[str, ...]:
    if not isinstance(raw, list) or any(
        not isinstance(symbol, str) or not symbol for symbol in raw
    ):
        raise SessionStateCodecError("closed_position_symbols_invalid")
    if len(raw) != len(set(raw)):
        raise SessionStateCodecError("closed_position_symbols_invalid")
    return tuple(sorted(raw))


def _parse_position_state_versions(raw: dict) -> dict[str, int]:
    if not isinstance(raw, dict) or any(
        not isinstance(symbol, str)
        or not symbol
        or not _is_nonnegative_int(version)
        for symbol, version in raw.items()
    ):
        raise SessionStateCodecError("position_state_versions_invalid")
    return dict(raw)


def _parse_position_high_water(raw: dict) -> dict[str, PositionHighWater]:
    if not isinstance(raw, dict):
        raise SessionStateCodecError("position_high_water_invalid")
    parsed: dict[str, PositionHighWater] = {}
    for symbol, value in raw.items():
        if not isinstance(symbol, str) or not symbol or not isinstance(value, dict):
            raise SessionStateCodecError("position_high_water_invalid")
        avg_entry_price = value.get("avg_entry_price")
        high_water_price = value.get("high_water_price")
        if (
            not isinstance(avg_entry_price, (int, float))
            or isinstance(avg_entry_price, bool)
            or not isfinite(avg_entry_price)
            or avg_entry_price <= 0
            or not isinstance(high_water_price, (int, float))
            or isinstance(high_water_price, bool)
            or not isfinite(high_water_price)
            or high_water_price <= 0
        ):
            raise SessionStateCodecError("position_high_water_invalid")
        parsed[symbol] = PositionHighWater(
            float(avg_entry_price),
            float(high_water_price),
        )
    return parsed


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
