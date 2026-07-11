"""Small, dependency-free technical indicator implementations."""

from __future__ import annotations

from math import sqrt

from .models import Bar


class IndicatorInputError(ValueError):
    pass


def _require_period(values: list[float], period: int) -> None:
    """Raise when a rolling calculation cannot be computed."""

    if period <= 0:
        raise IndicatorInputError("period must be greater than zero")
    if len(values) < period:
        raise IndicatorInputError("not enough values for requested period")


def sma(values: list[float], period: int) -> float:
    """Return the simple moving average of the latest period."""

    _require_period(values, period)
    window = values[-period:]
    return sum(window) / period


def _ema_series(values: list[float], period: int) -> list[float]:
    """Return the EMA series seeded with the first simple average."""

    _require_period(values, period)
    multiplier = 2 / (period + 1)
    result = [sum(values[:period]) / period]
    for value in values[period:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def ema(values: list[float], period: int) -> float:
    """Return the latest exponential moving average."""

    return _ema_series(values, period)[-1]


def rsi(values: list[float], period: int = 14) -> float:
    """Return the Relative Strength Index on a 0-100 scale."""

    if period <= 0:
        raise IndicatorInputError("period must be greater than zero")
    if len(values) < period + 1:
        raise IndicatorInputError("not enough values for requested RSI period")

    gains: list[float] = []
    losses: list[float] = []
    recent = values[-(period + 1) :]
    for previous, current in zip(recent, recent[1:]):
        change = current - previous
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    if average_loss == 0:
        return 100.0
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def macd(
    values: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[float, float, float]:
    """Return MACD line, signal line, and histogram."""

    if fast >= slow:
        raise IndicatorInputError("fast period must be smaller than slow period")
    _require_period(values, slow + signal)

    fast_values = _ema_series(values, fast)
    slow_values = _ema_series(values, slow)
    offset = len(fast_values) - len(slow_values)
    macd_values = [
        fast_value - slow_value
        for fast_value, slow_value in zip(fast_values[offset:], slow_values)
    ]
    signal_line = ema(macd_values, signal)
    macd_line = macd_values[-1]
    return macd_line, signal_line, macd_line - signal_line


def bollinger_bands(
    values: list[float],
    period: int = 20,
    deviations: float = 2.0,
) -> tuple[float, float, float]:
    """Return lower, middle, and upper Bollinger Bands."""

    _require_period(values, period)
    window = values[-period:]
    middle = sum(window) / period
    variance = sum((value - middle) ** 2 for value in window) / period
    spread = sqrt(variance) * deviations
    return middle - spread, middle, middle + spread


def atr(bars: list[Bar], period: int = 14) -> float:
    """Return Average True Range using the latest period."""

    if period <= 0:
        raise IndicatorInputError("period must be greater than zero")
    if len(bars) < period + 1:
        raise IndicatorInputError("not enough bars for requested ATR period")

    true_ranges: list[float] = []
    recent = bars[-(period + 1) :]
    for previous, current in zip(recent, recent[1:]):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return sum(true_ranges) / period


def rate_of_change(values: list[float], period: int) -> float:
    """Return percentage price change over the lookback period."""

    if period <= 0:
        raise IndicatorInputError("period must be greater than zero")
    if len(values) < period + 1:
        raise IndicatorInputError("not enough values for requested rate of change period")

    previous = values[-(period + 1)]
    if previous == 0:
        raise IndicatorInputError("rate of change is undefined when prior value is zero")
    return (values[-1] / previous - 1) * 100


def donchian_channel(values: list[float], period: int) -> tuple[float, float]:
    """Return lower and upper channel bounds for the latest period."""

    _require_period(values, period)
    window = values[-period:]
    return min(window), max(window)


def stochastic_oscillator(bars: list[Bar], period: int = 14) -> float:
    """Return fast stochastic percent K on a 0-100 scale."""

    _require_period([bar.close for bar in bars], period)
    window = bars[-period:]
    lowest_low = min(bar.low for bar in window)
    highest_high = max(bar.high for bar in window)
    if highest_high == lowest_low:
        return 50.0
    return (window[-1].close - lowest_low) / (highest_high - lowest_low) * 100


def average_volume(bars: list[Bar], period: int = 20) -> float:
    """Return the average volume over the latest period."""

    _require_period([bar.volume for bar in bars], period)
    return sum(bar.volume for bar in bars[-period:]) / period
