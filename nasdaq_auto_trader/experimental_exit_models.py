from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True, slots=True)
class ExitPolicyError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class ExitPolicy:
    stop_mode: Literal["legacy", "fixed", "entry_atr"] = "fixed"
    fixed_stop_pct: float = .08
    fixed_take_profit_pct: float = .16
    trailing_activation_pct: float = .08
    trailing_drawdown_pct: float = .04
    atr_period: int = 14
    atr_multiplier: float = 3.0
    min_stop_pct: float = .005
    max_stop_pct: float = .10
    emergency_stop_pct: float | None = None
    bar_interval: str = "1Day"
    block_conflicting_entry: bool = False
    completed_bar_only_general: bool = False
    minimum_general_hold_minutes: float = 0

    def __post_init__(self) -> None:
        fractions = (self.fixed_stop_pct, self.fixed_take_profit_pct,
                     self.trailing_activation_pct, self.trailing_drawdown_pct,
                     self.min_stop_pct, self.max_stop_pct)
        if any(not isfinite(value) or not 0 < value < 1 for value in fractions):
            raise ExitPolicyError("exit percentages must be finite fractions between zero and one")
        if self.min_stop_pct > self.max_stop_pct:
            raise ExitPolicyError("minimum stop exceeds maximum stop")
        if self.stop_mode not in ("legacy", "fixed", "entry_atr"):
            raise ExitPolicyError("unknown stop mode")
        if self.atr_period <= 0 or not isfinite(self.atr_multiplier) or self.atr_multiplier <= 0:
            raise ExitPolicyError("ATR period and multiplier must be positive")
        if not isfinite(self.minimum_general_hold_minutes) or self.minimum_general_hold_minutes < 0:
            raise ExitPolicyError("minimum holding minutes must be finite and nonnegative")
        if self.emergency_stop_pct is not None and not 0 < self.emergency_stop_pct < 1:
            raise ExitPolicyError("emergency stop must be a fraction between zero and one")
        if self.stop_mode == "legacy" and self.emergency_stop_pct is not None:
            raise ExitPolicyError("legacy policy does not support an emergency stop")
        if not self.bar_interval:
            raise ExitPolicyError("bar interval must be explicitly labelled")


@dataclass(frozen=True, slots=True)
class EntryVolatility:
    atr: float | None
    bar_timestamp: str


@dataclass(frozen=True, slots=True)
class ExitPositionState:
    symbol: str
    entry_price: float
    qty: float
    entry_atr: float | None
    initial_stop_price: float | None
    high_water_price: float
    trailing_active: bool
    entry_timestamp: str
    entry_bar_timestamp: str
    last_general_bar_timestamp: str
    emergency_stop_price: float | None = None


@dataclass(frozen=True, slots=True)
class ExitDiagnostics:
    symbol: str
    stop_mode: str
    profile_fingerprint: str
    price: float
    price_source: str
    price_timestamp: str | None
    bar_timestamp: str
    bar_interval: str
    entry_price: float | None
    fixed_stop_price: float | None
    current_atr: float | None
    entry_atr: float | None
    atr_stop_price: float | None
    initial_stop_price: float | None
    effective_stop_price: float | None
    emergency_stop_price: float | None
    high_water_price: float | None
    trailing_active: bool
    trailing_price: float | None
    buy_score: int | None = None
    sell_score: int | None = None
    limitation: str = "account mark has no timestamp; bar interval is caller-declared"
