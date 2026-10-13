from __future__ import annotations

import json
from dataclasses import asdict
from math import isfinite
from typing import TypeAlias, assert_never

from .experimental_exit_models import (
    EntryVolatility,
    ExitPolicy,
    ExitPolicyError,
    ExitPositionState,
)
from .indicators import atr
from .models import Bar
from .strategy_config import StrategyConfig

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def valid_atr(bars: list[Bar], period: int) -> float | None:
    if len(bars) < period + 1:
        return None
    recent = bars[-period - 1:]
    if any(not all(isfinite(value) and value > 0 for value in (bar.high, bar.low, bar.close))
           or bar.high < bar.low for bar in recent):
        return None
    value = atr(bars, period)
    return value if isfinite(value) and value > 0 else None


def initial_stop(policy: ExitPolicy, config: StrategyConfig, price: float,
                 volatility: float | None) -> float | None:
    match policy.stop_mode:
        case "fixed":
            return price * (1 - policy.fixed_stop_pct)
        case "entry_atr":
            if volatility is None:
                return None
            distance = volatility * policy.atr_multiplier
            if not policy.min_stop_pct <= distance / price <= policy.max_stop_pct:
                return None
            return price - distance
        case "legacy":
            fixed = price * (1 - config.stop_loss_pct)
            return max(fixed, price - volatility * config.atr_stop_multiplier) if volatility else fixed
        case unreachable:
            assert_never(unreachable)


def effective_stop(policy: ExitPolicy, price: float, primary: float | None) -> float | None:
    emergency = None if policy.emergency_stop_pct is None else price * (1 - policy.emergency_stop_pct)
    thresholds = [value for value in (primary, emergency) if value is not None]
    return max(thresholds) if thresholds else None


def retained_stop(state: ExitPositionState) -> float | None:
    thresholds = [value for value in (state.initial_stop_price, state.emergency_stop_price) if value is not None]
    return max(thresholds) if thresholds else None


class ExitStateStore:
    def __init__(self, fingerprint: str) -> None:
        self.fingerprint = fingerprint
        self.positions: dict[str, ExitPositionState] = {}
        self.pending: dict[str, EntryVolatility] = {}

    def export_state(self) -> str:
        return json.dumps({"version": 2, "fingerprint": self.fingerprint,
                           "positions": [asdict(state) for state in self.positions.values()],
                           "pending": {symbol: asdict(state) for symbol, state in self.pending.items()}},
                          allow_nan=False, sort_keys=True)

    def load_state(self, payload: str) -> None:
        parsed: JsonValue = json.loads(payload)
        if not isinstance(parsed, dict) or parsed.get("version") != 2:
            raise ExitPolicyError("invalid exit state version")
        if parsed.get("fingerprint") != self.fingerprint:
            raise ExitPolicyError("exit state profile fingerprint mismatch")
        rows, pending_rows = parsed.get("positions"), parsed.get("pending")
        if not isinstance(rows, list) or not isinstance(pending_rows, dict):
            raise ExitPolicyError("invalid exit state containers")
        positions: dict[str, ExitPositionState] = {}
        pending: dict[str, EntryVolatility] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ExitPolicyError("invalid position state")
            symbol = _text(row.get("symbol"))
            active = row.get("trailing_active")
            if not isinstance(active, bool) or symbol in positions:
                raise ExitPolicyError("invalid trailing state or duplicate symbol")
            positions[symbol] = ExitPositionState(
                symbol, _positive(row.get("entry_price")), _positive(row.get("qty")),
                _optional_positive(row.get("entry_atr")), _optional_positive(row.get("initial_stop_price")),
                _positive(row.get("high_water_price")), active, _text(row.get("entry_timestamp")),
                _text(row.get("entry_bar_timestamp")), _text(row.get("last_general_bar_timestamp")),
                _optional_positive(row.get("emergency_stop_price")),
            )
        for symbol, row in pending_rows.items():
            if not isinstance(row, dict):
                raise ExitPolicyError("invalid pending entry state")
            pending[symbol] = EntryVolatility(_optional_positive(row.get("atr")), _text(row.get("bar_timestamp")))
        self.positions, self.pending = positions, pending


def _positive(value: JsonValue) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or value <= 0:
        raise ExitPolicyError("exit state number must be finite and positive")
    return float(value)


def _optional_positive(value: JsonValue) -> float | None:
    return None if value is None else _positive(value)


def _text(value: JsonValue) -> str:
    if not isinstance(value, str):
        raise ExitPolicyError("exit state timestamp or symbol must be text")
    return value
