from __future__ import annotations

import math

from .sell_monitor_types import JsonObject


def _first_float(
    primary: JsonObject,
    secondary: JsonObject,
    *keys: str,
    default: float = 0.0,
) -> float:
    for payload in (primary, secondary):
        if not isinstance(payload, dict):
            continue
        for key in keys:
            value = payload.get(key)
            if value in (None, ""):
                continue
            try:
                return float(str(value).replace(",", ""))
            except ValueError:
                continue
    return default


def _floor_to_cent(value: float) -> float:
    return math.floor(value * 100) / 100
