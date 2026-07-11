from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Mapping, TypeAlias

from nasdaq_auto_trader.config_types import RunMode

from .resources import ResourceLoadError, read_quant_resource


JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)
JsonObject: TypeAlias = dict[str, JsonValue]
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
DEFAULT_UNIVERSE_RESOURCE = "defaults/nasdaq_100_universe.json"
MAX_UNIVERSE_SYMBOLS = 120
MAX_LIVE_AGE_DAYS = 120


class UniverseSnapshotError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class UniverseSymbol:
    symbol: str
    index_weight_pct: float | None = None


@dataclass(frozen=True, slots=True)
class UniverseSnapshot:
    schema_version: int
    universe_id: str
    effective_date: date
    source_url: str
    source_notes: tuple[str, ...]
    symbols: tuple[UniverseSymbol, ...]
    checksum: str


@dataclass(frozen=True, slots=True)
class UniverseFreshness:
    age_days: int
    warnings: tuple[str, ...]
    blocked_reason: str = ""


def load_default_universe() -> UniverseSnapshot:
    try:
        raw_text = read_quant_resource(DEFAULT_UNIVERSE_RESOURCE)
    except ResourceLoadError as exc:
        raise UniverseSnapshotError(exc.reason) from exc
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise UniverseSnapshotError("universe_resource_invalid_json") from exc
    if not isinstance(payload, dict):
        raise UniverseSnapshotError("universe_root_invalid")
    return parse_universe_snapshot(payload)


def parse_universe_snapshot(
    payload: Mapping[str, JsonValue],
    *,
    verify_checksum: bool = True,
) -> UniverseSnapshot:
    schema_version = _required_int(payload, "schema_version")
    if schema_version != 1:
        raise UniverseSnapshotError("universe_schema_version_unsupported")
    universe_id = _required_text(payload, "universe_id")
    if universe_id != "nasdaq_100":
        raise UniverseSnapshotError("universe_id_invalid")
    effective_date = _effective_date(_required_text(payload, "effective_date"))
    source_url = _required_text(payload, "source_url")
    if not source_url.startswith("https://"):
        raise UniverseSnapshotError("universe_source_url_invalid")
    source_notes = _source_notes(payload.get("source_notes"))
    symbols = _symbols(payload.get("symbols"))
    checksum = _required_text(payload, "checksum")
    if verify_checksum and checksum != universe_checksum(symbols):
        raise UniverseSnapshotError("universe_checksum_mismatch")
    return UniverseSnapshot(
        schema_version,
        universe_id,
        effective_date,
        source_url,
        source_notes,
        symbols,
        checksum,
    )


def universe_checksum(symbols: tuple[UniverseSymbol, ...]) -> str:
    canonical = "\n".join(sorted(item.symbol for item in symbols)).encode()
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def universe_freshness(
    snapshot: UniverseSnapshot,
    mode: RunMode,
    today: date,
) -> UniverseFreshness:
    age_days = max((today - snapshot.effective_date).days, 0)
    if age_days <= MAX_LIVE_AGE_DAYS:
        return UniverseFreshness(age_days, ())
    if mode == "live":
        return UniverseFreshness(age_days, (), "universe_snapshot_stale")
    return UniverseFreshness(age_days, ("universe_snapshot_stale",))


def _required_text(payload: Mapping[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise UniverseSnapshotError(f"universe_{key}_invalid")
    return value.strip()


def _required_int(payload: Mapping[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise UniverseSnapshotError(f"universe_{key}_invalid")
    return value


def _effective_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise UniverseSnapshotError("universe_effective_date_invalid") from exc


def _source_notes(value: JsonValue | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise UniverseSnapshotError("universe_source_notes_invalid")
    notes = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(notes) != len(value):
        raise UniverseSnapshotError("universe_source_notes_invalid")
    return notes


def _symbols(value: JsonValue | None) -> tuple[UniverseSymbol, ...]:
    if not isinstance(value, list):
        raise UniverseSnapshotError("universe_symbols_invalid")
    if not value:
        raise UniverseSnapshotError("universe_symbols_empty")
    if len(value) > MAX_UNIVERSE_SYMBOLS:
        raise UniverseSnapshotError("universe_symbols_oversized")
    parsed = tuple(_symbol(item) for item in value)
    names = [item.symbol for item in parsed]
    if len(set(names)) != len(names):
        raise UniverseSnapshotError("universe_symbol_duplicate")
    return parsed


def _symbol(value: JsonValue) -> UniverseSymbol:
    if not isinstance(value, dict):
        raise UniverseSnapshotError("universe_symbol_invalid")
    raw_symbol = value.get("symbol")
    if not isinstance(raw_symbol, str):
        raise UniverseSnapshotError("universe_symbol_invalid")
    symbol = raw_symbol.strip().upper()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise UniverseSnapshotError("universe_symbol_invalid")
    raw_weight = value.get("index_weight_pct")
    weight = _optional_weight(raw_weight)
    return UniverseSymbol(symbol, weight)


def _optional_weight(value: JsonValue | None) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise UniverseSnapshotError("universe_symbol_weight_invalid")
    weight = float(value)
    if not math.isfinite(weight) or weight < 0:
        raise UniverseSnapshotError("universe_symbol_weight_invalid")
    return weight
