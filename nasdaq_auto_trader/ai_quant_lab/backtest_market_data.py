from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from math import isfinite

from nasdaq_auto_trader.quant_data.features import PriceBar
from nasdaq_auto_trader.quant_data.feature_statistics import (
    daily_sampling_compatible,
    normalized_timestamps,
)


def validate_backtest_market_data(
    bars_by_symbol: Mapping[str, Sequence[PriceBar]],
    initial_cash: float,
) -> tuple[int, str | None]:
    if not isfinite(initial_cash) or initial_cash <= 0:
        return 0, "initial_cash_invalid"
    if not bars_by_symbol:
        return 0, "market_data_missing"
    reference = tuple(next(iter(bars_by_symbol.values())))
    if len(reference) < 3:
        return 0, "not_enough_bars"
    reference_timestamps = normalized_timestamps(reference)
    if reference_timestamps is None:
        return 0, "market_data_timestamp_invalid"
    if not _timestamps_are_monotonic(reference_timestamps):
        return 0, "market_data_timestamps_not_monotonic"
    for bars in bars_by_symbol.values():
        if len(bars) != len(reference):
            return 0, "market_data_timestamps_misaligned"
        timestamps = normalized_timestamps(bars)
        if timestamps is None:
            return 0, "market_data_timestamp_invalid"
        if not _timestamps_are_monotonic(timestamps):
            return 0, "market_data_timestamps_not_monotonic"
        if timestamps != reference_timestamps:
            return 0, "market_data_timestamps_misaligned"
        if any(not _bar_is_valid(bar) for bar in bars):
            return 0, "market_data_values_invalid"
    if not daily_sampling_compatible(reference_timestamps):
        return 0, "market_data_frequency_not_daily"
    return len(reference), None


def _timestamps_are_monotonic(timestamps: tuple[datetime, ...]) -> bool:
    return all(
        timestamps[index] > timestamps[index - 1]
        for index in range(1, len(timestamps))
    )


def _bar_is_valid(bar: PriceBar) -> bool:
    prices = (bar.open, bar.high, bar.low, bar.close)
    return (
        all(isfinite(value) and value > 0 for value in prices)
        and isfinite(bar.volume)
        and bar.volume >= 0
    )
