from __future__ import annotations

from dataclasses import dataclass, replace
from math import sqrt


@dataclass(frozen=True, slots=True)
class PriceBar:
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    bid: float = 0.0
    ask: float = 0.0


@dataclass(frozen=True, slots=True)
class FeatureRow:
    symbol: str
    current_price: float
    daily_return: float
    intraday_return: float
    gap_percent: float
    rolling_return_5d: float
    rolling_return_20d: float
    rolling_return_60d: float
    rolling_return_120d: float
    sma_5: float
    sma_20: float
    sma_60: float
    sma_120: float
    ema_12: float
    ema_26: float
    macd: float
    relative_strength_20d: float
    relative_strength_60d: float
    relative_strength_120d: float
    cross_sectional_rank: float
    time_series_momentum: float
    volatility_20d: float
    volatility_60d: float
    atr_14: float
    realized_volatility: float
    beta_to_qqq: float
    volatility_regime: str
    rsi_14: float
    zscore_20: float
    bollinger_position: float
    short_term_reversal: float
    dollar_volume: float
    avg_volume_20d: float
    spread_bps: float
    turnover_ratio: float
    momentum_factor: float
    low_volatility_factor: float
    liquidity_factor: float
    quality_factor: float
    growth_factor: float
    value_factor: float
    missing_data_ratio: float
    stale_data_flag: bool
    outlier_flag: bool
    corporate_action_flag: bool
    survivorship_warning_flag: bool


def calculate_feature_rows(
    bars_by_symbol: dict[str, list[PriceBar]],
    benchmark_symbol: str = "QQQ",
) -> dict[str, FeatureRow]:
    benchmark_returns = _returns(bars_by_symbol.get(benchmark_symbol, []))
    rows = {
        symbol: _feature_row(symbol, bars, benchmark_returns)
        for symbol, bars in bars_by_symbol.items()
        if bars
    }
    ranked = _rank_cross_sectional(rows)
    return {
        symbol: _with_cross_sectional_rank(row, ranked.get(symbol, 0.0))
        for symbol, row in rows.items()
    }


def _feature_row(
    symbol: str,
    bars: list[PriceBar],
    benchmark_returns: list[float],
) -> FeatureRow:
    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    volumes = [bar.volume for bar in bars]
    latest = bars[-1]
    returns = _returns(bars)
    vol20 = _stdev(returns[-20:])
    vol60 = _stdev(returns[-60:])
    avg_volume_20d = _mean(volumes[-20:])
    spread_bps = _spread_bps(latest.bid, latest.ask)
    rolling20 = _rolling_return(closes, 20)
    return FeatureRow(
        symbol=symbol,
        current_price=latest.close,
        daily_return=returns[-1] if returns else 0.0,
        intraday_return=_safe_return(latest.open, latest.close),
        gap_percent=_gap_percent(bars),
        rolling_return_5d=_rolling_return(closes, 5),
        rolling_return_20d=rolling20,
        rolling_return_60d=_rolling_return(closes, 60),
        rolling_return_120d=_rolling_return(closes, 120),
        sma_5=_mean(closes[-5:]),
        sma_20=_mean(closes[-20:]),
        sma_60=_mean(closes[-60:]),
        sma_120=_mean(closes[-120:]),
        ema_12=_ema(closes, 12),
        ema_26=_ema(closes, 26),
        macd=_ema(closes, 12) - _ema(closes, 26),
        relative_strength_20d=rolling20 - _rolling_benchmark(benchmark_returns, 20),
        relative_strength_60d=_rolling_return(closes, 60) - _rolling_benchmark(benchmark_returns, 60),
        relative_strength_120d=_rolling_return(closes, 120) - _rolling_benchmark(benchmark_returns, 120),
        cross_sectional_rank=0.0,
        time_series_momentum=rolling20,
        volatility_20d=vol20,
        volatility_60d=vol60,
        atr_14=_atr(highs, lows, closes, 14),
        realized_volatility=vol20 * sqrt(252),
        beta_to_qqq=_beta(returns[-60:], benchmark_returns[-60:]),
        volatility_regime="high_volatility" if vol20 > vol60 and vol20 > 0 else "low_volatility",
        rsi_14=_rsi(closes, 14),
        zscore_20=_zscore(closes[-20:]),
        bollinger_position=_bollinger_position(closes[-20:]),
        short_term_reversal=-_rolling_return(closes, 5),
        dollar_volume=latest.close * latest.volume,
        avg_volume_20d=avg_volume_20d,
        spread_bps=spread_bps,
        turnover_ratio=latest.volume / avg_volume_20d if avg_volume_20d > 0 else 0.0,
        momentum_factor=rolling20,
        low_volatility_factor=1 / (1 + vol20),
        liquidity_factor=latest.close * avg_volume_20d,
        quality_factor=0.0,
        growth_factor=0.0,
        value_factor=0.0,
        missing_data_ratio=_missing_data_ratio(bars),
        stale_data_flag=False,
        outlier_flag=abs(returns[-1]) > 0.25 if returns else False,
        corporate_action_flag=False,
        survivorship_warning_flag=True,
    )


def _with_cross_sectional_rank(row: FeatureRow, rank: float) -> FeatureRow:
    return replace(row, cross_sectional_rank=rank)


def _rank_cross_sectional(rows: dict[str, FeatureRow]) -> dict[str, float]:
    ordered = sorted(
        rows.values(),
        key=lambda row: (row.rolling_return_20d, row.symbol),
    )
    if len(ordered) <= 1:
        return {row.symbol: 1.0 for row in ordered}
    return {row.symbol: index / (len(ordered) - 1) for index, row in enumerate(ordered)}


def _returns(bars: list[PriceBar]) -> list[float]:
    return [_safe_return(bars[index - 1].close, bars[index].close) for index in range(1, len(bars))]


def _rolling_return(values: list[float], days: int) -> float:
    if len(values) <= days:
        return 0.0
    return _safe_return(values[-days - 1], values[-1])


def _rolling_benchmark(returns: list[float], days: int) -> float:
    if len(returns) < days:
        return 0.0
    total = 1.0
    for value in returns[-days:]:
        total *= 1 + value
    return total - 1


def _safe_return(start: float, end: float) -> float:
    return (end / start) - 1 if start > 0 else 0.0


def _gap_percent(bars: list[PriceBar]) -> float:
    if len(bars) < 2:
        return 0.0
    return _safe_return(bars[-2].close, bars[-1].open)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    return sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2 / (period + 1)
    ema = values[0]
    for value in values[1:]:
        ema = alpha * value + (1 - alpha) * ema
    return ema


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    ranges: list[float] = []
    for index in range(1, len(closes)):
        ranges.append(max(highs[index] - lows[index], abs(highs[index] - closes[index - 1]), abs(lows[index] - closes[index - 1])))
    return _mean(ranges[-period:])


def _rsi(values: list[float], period: int) -> float:
    if len(values) <= period:
        return 50.0
    deltas = [values[index] - values[index - 1] for index in range(1, len(values))]
    gains = [max(delta, 0.0) for delta in deltas[-period:]]
    losses = [abs(min(delta, 0.0)) for delta in deltas[-period:]]
    avg_loss = _mean(losses)
    if avg_loss == 0:
        return 100.0
    relative_strength = _mean(gains) / avg_loss
    return 100 - (100 / (1 + relative_strength))


def _zscore(values: list[float]) -> float:
    stdev = _stdev(values)
    return (values[-1] - _mean(values)) / stdev if values and stdev > 0 else 0.0


def _bollinger_position(values: list[float]) -> float:
    stdev = _stdev(values)
    if not values or stdev == 0:
        return 0.5
    lower = _mean(values) - 2 * stdev
    upper = _mean(values) + 2 * stdev
    return (values[-1] - lower) / (upper - lower)


def _beta(returns: list[float], benchmark_returns: list[float]) -> float:
    count = min(len(returns), len(benchmark_returns))
    if count < 2:
        return 0.0
    stock = returns[-count:]
    benchmark = benchmark_returns[-count:]
    avg_stock = _mean(stock)
    avg_benchmark = _mean(benchmark)
    variance = sum((value - avg_benchmark) ** 2 for value in benchmark)
    if variance == 0:
        return 0.0
    covariance = sum((stock[index] - avg_stock) * (benchmark[index] - avg_benchmark) for index in range(count))
    return covariance / variance


def _spread_bps(bid: float, ask: float) -> float:
    if bid <= 0 or ask <= 0 or ask < bid:
        return 0.0
    return ((ask - bid) / ((ask + bid) / 2)) * 10_000


def _missing_data_ratio(bars: list[PriceBar]) -> float:
    missing = sum(1 for bar in bars if bar.close <= 0 or bar.volume < 0)
    return missing / len(bars) if bars else 1.0
