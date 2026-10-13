from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from math import isfinite

from .indicators import IndicatorInputError, atr
from .models import Bar, Position
from .strategy import TechnicalStrategy


@dataclass(frozen=True, slots=True)
class ExitDiagnostics:
    schema_version: int = 1
    config_digest: str = ""
    price_source: str = "unavailable"
    price_timestamp: str | None = None
    bar_timestamp: str | None = None
    decision_price: float | None = None
    average_entry: float | None = None
    quantity: float | None = None
    fixed_stop_price: float | None = None
    fixed_take_profit_price: float | None = None
    atr_value: float | None = None
    raw_atr_value: float | None = None
    atr_status: str = "insufficient_history"
    atr_period: int = 14
    atr_stop_price: float | None = None
    atr_take_profit_price: float | None = None
    effective_stop_price: float | None = None
    high_water: float | None = None
    trailing_price: float | None = None
    trailing_activated: bool = False
    buy_score: int | None = None
    sell_score: int | None = None
    indicator_status: str = "insufficient_history"
    corrected_exits: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), allow_nan=False)


def exit_diagnostics(
    strategy: TechnicalStrategy, bars: list[Bar], position: Position | None,
) -> ExitDiagnostics:
    config = strategy.config
    digest = sha256(json.dumps(asdict(config), sort_keys=True).encode()).hexdigest()[:16]
    price = bars[-1].close if bars else None
    source = "bar_close" if bars else "unavailable"
    timestamp = bars[-1].timestamp if bars else None
    if position is not None and position.qty > 0 and position.market_value > 0:
        price = position.market_value / position.qty
        source, timestamp = "broker_position_market_value_per_share", None
    price = _finite(price)
    raw_atr = None
    atr_status = "insufficient_history"
    if len(bars) > config.atr_period:
        try:
            raw_atr = atr(bars, config.atr_period)
            atr_status = "available"
        except IndicatorInputError:
            atr_status = "invalid_indicator_history"
    if raw_atr is not None and not isfinite(raw_atr):
        raw_atr, atr_status = None, "invalid_nonfinite"
    if raw_atr is not None and raw_atr <= 0:
        atr_status = "invalid_nonpositive"
        if not config.corrected_exits:
            atr_status += "_legacy_active"
    atr_value = raw_atr if raw_atr is not None and raw_atr > 0 else None
    guard_atr = atr_value if config.corrected_exits else raw_atr
    entry = _finite(position.avg_entry_price) if position else None
    fixed_stop = entry * (1 - config.stop_loss_pct) if entry is not None else None
    atr_stop = (
        entry - guard_atr * config.atr_stop_multiplier
        if entry is not None and guard_atr is not None else None
    )
    high = _finite(position.high_water_price) if position else None
    activated = bool(
        config.trailing_stop_enabled and high is not None and entry is not None
        and config.trailing_stop_activation_pct > 0 and config.trailing_stop_pct > 0
        and high >= entry * (1 + config.trailing_stop_activation_pct)
    )
    buy_score = sell_score = None
    indicator_status = "insufficient_history"
    if bars and any(not isfinite(bar.close) or bar.close <= 0 for bar in bars):
        indicator_status = "invalid_indicator_history"
    elif len(bars) >= strategy._minimum_bars():
        try:
            closes = [bar.close for bar in bars]
            buy_score, _ = strategy._buy_score(closes, bars, closes[-1])
            sell_score, _ = strategy._sell_score(closes, bars, closes[-1])
            indicator_status = "available"
        except IndicatorInputError:
            buy_score = sell_score = None
            indicator_status = "invalid_indicator_history"
    return ExitDiagnostics(
        config_digest=digest, price_source=source, price_timestamp=timestamp,
        bar_timestamp=bars[-1].timestamp if bars else None, decision_price=price,
        average_entry=entry, quantity=_finite(position.qty) if position else None,
        fixed_stop_price=fixed_stop,
        fixed_take_profit_price=entry * (1 + config.take_profit_pct) if entry is not None else None,
        atr_value=atr_value, raw_atr_value=raw_atr, atr_status=atr_status,
        atr_period=config.atr_period, atr_stop_price=atr_stop,
        atr_take_profit_price=(
            entry + guard_atr * config.atr_take_profit_multiplier
            if entry is not None and guard_atr is not None else None
        ),
        effective_stop_price=max(fixed_stop, atr_stop) if fixed_stop is not None and atr_stop is not None else fixed_stop,
        high_water=high,
        trailing_price=high * (1 - config.trailing_stop_pct) if activated and high is not None else None,
        trailing_activated=activated, buy_score=buy_score, sell_score=sell_score,
        indicator_status=indicator_status, corrected_exits=config.corrected_exits,
    )


def _finite(value: float | None) -> float | None:
    return value if value is not None and isfinite(value) else None
