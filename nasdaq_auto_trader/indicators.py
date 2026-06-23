"""유명 기술적 지표들을 외부 라이브러리 없이 계산한다."""

from __future__ import annotations

from math import sqrt

from .models import Bar


def _require_period(values: list[float], period: int) -> None:
    """기간 값이 말이 되는지 먼저 검사한다."""

    if period <= 0:
        raise ValueError("period must be greater than zero")
    if len(values) < period:
        raise ValueError("not enough values for requested period")


def sma(values: list[float], period: int) -> float:
    """마지막 period개 값의 단순 이동평균을 계산한다."""

    _require_period(values, period)
    window = values[-period:]
    return sum(window) / period


def _ema_series(values: list[float], period: int) -> list[float]:
    """EMA 전체 흐름을 만들기 위해 각 지점의 값을 차례로 계산한다."""

    _require_period(values, period)
    multiplier = 2 / (period + 1)
    result = [sum(values[:period]) / period]
    for value in values[period:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def ema(values: list[float], period: int) -> float:
    """마지막 값 기준의 지수 이동평균을 계산한다."""

    return _ema_series(values, period)[-1]


def rsi(values: list[float], period: int = 14) -> float:
    """최근 상승폭과 하락폭으로 RSI를 계산한다."""

    if len(values) < period + 1:
        raise ValueError("not enough values for requested RSI period")

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
    """MACD 선, 신호선, 히스토그램을 계산한다."""

    if fast >= slow:
        raise ValueError("fast period must be smaller than slow period")
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
    """볼린저 밴드의 아래선, 중간선, 위선을 계산한다."""

    _require_period(values, period)
    window = values[-period:]
    middle = sum(window) / period
    variance = sum((value - middle) ** 2 for value in window) / period
    spread = sqrt(variance) * deviations
    return middle - spread, middle, middle + spread


def atr(bars: list[Bar], period: int = 14) -> float:
    """가격 변동폭을 보는 ATR 값을 계산한다."""

    if len(bars) < period + 1:
        raise ValueError("not enough bars for requested ATR period")

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
