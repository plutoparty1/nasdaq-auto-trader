"""Offline fractional-return statistics; unavailable or invalid estimates are zero.

No risk-free series is implied: ratio inputs are excess returns supplied by the
caller (raw returns mean an explicit zero hurdle). Annualization is caller-owned.
"""

from collections.abc import Sequence
from math import expm1, isfinite, log, sqrt
from statistics import fmean, stdev


def simple_return(start: float, end: float) -> float:
    if not isfinite(start) or not isfinite(end) or start <= 0 or end < 0:
        return 0.0
    value = end / start - 1.0
    return value if isfinite(value) else 0.0


def simple_returns(prices: Sequence[float]) -> tuple[float, ...]:
    return tuple(simple_return(start, end) for start, end in zip(prices, prices[1:]))


def sample_std(values: Sequence[float]) -> float:
    """Sample standard deviation (ddof=1); fewer than two values are unavailable."""
    if len(values) < 2 or any(not isfinite(value) for value in values):
        return 0.0
    return stdev(values)


def annualized_volatility(returns: Sequence[float], periods_per_year: float) -> float:
    if not isfinite(periods_per_year) or periods_per_year <= 0:
        return 0.0
    value = sample_std(returns) * sqrt(periods_per_year)
    return value if isfinite(value) else 0.0


def downside_deviation(returns: Sequence[float]) -> float:
    """Root mean squared negative excess returns over ALL observations (ddof=0)."""
    if not returns or any(not isfinite(value) for value in returns):
        return 0.0
    scale = max(abs(min(value, 0.0)) for value in returns)
    if scale == 0:
        return 0.0
    return scale * sqrt(fmean((min(value, 0.0) / scale) ** 2 for value in returns))


def sharpe_ratio(returns: Sequence[float], periods_per_year: float) -> float:
    return _annualized_ratio(returns, sample_std(returns), periods_per_year)


def sortino_ratio(returns: Sequence[float], periods_per_year: float) -> float:
    return _annualized_ratio(returns, downside_deviation(returns), periods_per_year)


def _annualized_ratio(returns: Sequence[float], risk: float, periods: float) -> float:
    if not returns or risk <= 0 or not isfinite(periods) or periods <= 0:
        return 0.0
    value = (fmean(returns) / risk) * sqrt(periods)
    return value if isfinite(value) else 0.0


def geometric_cagr(equity: Sequence[float], elapsed_years: float) -> float:
    if len(equity) < 2 or not isfinite(elapsed_years) or elapsed_years <= 0:
        return 0.0
    if any(not isfinite(value) or value <= 0 for value in equity):
        return 0.0
    try:
        value = expm1((log(equity[-1]) - log(equity[0])) / elapsed_years)
    except OverflowError:
        return 0.0
    return value if isfinite(value) else 0.0


def max_drawdown(equity: Sequence[float]) -> float:
    """Largest peak-to-trough loss as a nonnegative fraction, including recovery."""
    if not equity or any(not isfinite(value) or value <= 0 for value in equity):
        return 0.0
    peak = equity[0]
    drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = max(drawdown, 1.0 - value / peak)
    return drawdown


def beta(returns: Sequence[float], benchmark: Sequence[float]) -> float:
    """Covariance/benchmark variance; caller must align both interval endpoints."""
    if len(returns) < 2 or len(returns) != len(benchmark):
        return 0.0
    if any(not isfinite(value) for value in (*returns, *benchmark)):
        return 0.0
    benchmark_mean = fmean(benchmark)
    stock_mean = fmean(returns)
    variance = sum((value - benchmark_mean) ** 2 for value in benchmark)
    if variance == 0:
        return 0.0
    covariance = sum((left - stock_mean) * (right - benchmark_mean) for left, right in zip(returns, benchmark, strict=True))
    value = covariance / variance
    return value if isfinite(value) else 0.0
