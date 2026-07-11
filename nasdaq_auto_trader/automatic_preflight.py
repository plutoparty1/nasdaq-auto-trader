from __future__ import annotations

from datetime import datetime

from .config import AppConfig
from .quant_data import universe_snapshot


def automatic_universe_block(config: AppConfig, now: datetime) -> str:
    try:
        snapshot = universe_snapshot.load_default_universe()
    except universe_snapshot.UniverseSnapshotError as exc:
        return exc.reason
    freshness = universe_snapshot.universe_freshness(
        snapshot,
        config.mode,
        now.date(),
    )
    return freshness.blocked_reason
