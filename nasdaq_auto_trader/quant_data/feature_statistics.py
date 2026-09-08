from collections.abc import Sequence
from datetime import datetime, timezone
from math import isfinite
from statistics import median
from typing import Protocol

from nasdaq_auto_trader.quant_analytics import annualized_volatility, beta, simple_return


class PriceObservation(Protocol):
    @property
    def timestamp(self) -> str: ...

    @property
    def close(self) -> float: ...


def normalized_timestamps(bars: Sequence[PriceObservation]) -> tuple[datetime, ...] | None:
    normalized: list[datetime] = []
    for bar in bars:
        try:
            parsed = datetime.fromisoformat(bar.timestamp.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        normalized.append(parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc))
    return tuple(normalized)


def daily_sampling_compatible(timestamps: Sequence[datetime]) -> bool:
    """Sanity-check declared daily bars, allowing DST/weekends but not weekly data.

    This does not establish exchange-calendar completeness. A 20-hour minimum
    tolerates close-time/DST shifts; median gaps above three days are too sparse.
    """
    gaps = tuple((end - start).total_seconds() for start, end in zip(timestamps, timestamps[1:]))
    return bool(gaps) and min(gaps) >= 20 * 3600 and median(gaps) <= 3 * 86400


def daily_realized_volatility(bars: Sequence[PriceObservation], returns: Sequence[float]) -> float:
    timestamps = normalized_timestamps(bars)
    if timestamps is None or not daily_sampling_compatible(timestamps):
        return 0.0
    return annualized_volatility(returns, 252.0)


def aligned_beta(bars: Sequence[PriceObservation], benchmark: Sequence[PriceObservation]) -> float:
    """Use only matching original return intervals; never bridge missing bars."""
    stock_times = normalized_timestamps(bars)
    benchmark_times = normalized_timestamps(benchmark)
    if stock_times is None or benchmark_times is None:
        return 0.0
    if any(end <= start for times in (stock_times, benchmark_times) for start, end in zip(times, times[1:])):
        return 0.0
    benchmark_intervals = {
        (benchmark_times[index - 1], benchmark_times[index]): simple_return(benchmark[index - 1].close, benchmark[index].close)
        for index in range(1, len(benchmark))
        if all(isfinite(bar.close) and bar.close > 0 for bar in benchmark[index - 1:index + 1])
    }
    stock_returns: list[float] = []
    benchmark_returns: list[float] = []
    for index in range(1, len(bars)):
        interval = stock_times[index - 1], stock_times[index]
        if interval not in benchmark_intervals or any(not isfinite(bar.close) or bar.close <= 0 for bar in bars[index - 1:index + 1]):
            continue
        stock_returns.append(simple_return(bars[index - 1].close, bars[index].close))
        benchmark_returns.append(benchmark_intervals[interval])
    return beta(stock_returns, benchmark_returns)
