from __future__ import annotations

from dataclasses import replace

from .models import PositionHighWater
from .session_safety_reservation import PersistedSafetyState


def merge_position_state(
    persisted: PersistedSafetyState,
    current: PersistedSafetyState,
) -> tuple[dict[str, PositionHighWater], tuple[str, ...], dict[str, int]]:
    persisted_closed = set(persisted.closed_position_symbols)
    current_closed = set(current.closed_position_symbols)
    symbols = (
        set(persisted.position_high_water)
        | set(current.position_high_water)
        | persisted_closed
        | current_closed
    )
    high_water: dict[str, PositionHighWater] = {}
    closed: set[str] = set()
    versions: dict[str, int] = {}
    for symbol in symbols:
        persisted_version = persisted.position_state_versions.get(symbol, 0)
        current_version = current.position_state_versions.get(symbol, 0)
        versions[symbol] = max(persisted_version, current_version)
        if persisted_version > current_version:
            _copy_position_state(
                symbol,
                persisted.position_high_water,
                persisted_closed,
                high_water,
                closed,
            )
        elif current_version > persisted_version:
            _copy_position_state(
                symbol,
                current.position_high_water,
                current_closed,
                high_water,
                closed,
            )
        else:
            _merge_equal_version_state(
                symbol,
                persisted,
                current,
                persisted_closed,
                current_closed,
                high_water,
                closed,
            )
    return high_water, tuple(sorted(closed)), versions


def _copy_position_state(
    symbol: str,
    source: dict[str, PositionHighWater],
    source_closed: set[str],
    high_water: dict[str, PositionHighWater],
    closed: set[str],
) -> None:
    if symbol in source_closed:
        closed.add(symbol)
    elif symbol in source:
        high_water[symbol] = source[symbol]
    else:
        closed.add(symbol)


def _merge_equal_version_state(
    symbol: str,
    persisted: PersistedSafetyState,
    current: PersistedSafetyState,
    persisted_closed: set[str],
    current_closed: set[str],
    high_water: dict[str, PositionHighWater],
    closed: set[str],
) -> None:
    if symbol in persisted_closed or symbol in current_closed:
        closed.add(symbol)
        return
    persisted_position = persisted.position_high_water.get(symbol)
    current_position = current.position_high_water.get(symbol)
    if persisted_position is None:
        if current_position is not None:
            high_water[symbol] = current_position
        return
    if current_position is None:
        high_water[symbol] = persisted_position
        return
    if persisted_position.avg_entry_price != current_position.avg_entry_price:
        high_water[symbol] = current_position
        return
    high_water[symbol] = replace(
        current_position,
        high_water_price=max(
            persisted_position.high_water_price,
            current_position.high_water_price,
        ),
    )
