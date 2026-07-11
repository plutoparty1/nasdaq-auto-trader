from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from .quant_data.features import PriceBar, calculate_feature_rows


@dataclass(frozen=True, slots=True)
class MarketRegime:
    trend: str
    volatility: str
    liquidity: str
    volume_state: str
    market_breadth: float
    average_market_correlation: float | None
    correlation_analysis_enabled: bool
    trade_allowed: bool
    risk_multiplier: float
    risk_flags: tuple[str, ...]


def classify_market_regime(
    bars_by_symbol: dict[str, list[PriceBar]],
) -> MarketRegime:
    rows = calculate_feature_rows(bars_by_symbol)
    if not rows:
        return MarketRegime(
            "unknown",
            "unknown",
            "insufficient",
            "unknown",
            0.0,
            None,
            False,
            False,
            0.0,
            ("market_data_missing",),
        )
    returns = [row.rolling_return_20d for row in rows.values()]
    breadth = sum(value > 0 for value in returns) / len(returns)
    trend_return = median(returns)
    trend = "uptrend" if trend_return > 0.02 and breadth >= 0.6 else "downtrend" if trend_return < -0.02 and breadth <= 0.4 else "sideways"
    volatility_value = median(row.realized_volatility for row in rows.values())
    volatility = "high_volatility" if volatility_value > 0.35 else "low_volatility"
    dollar_volume = median(row.dollar_volume for row in rows.values())
    liquidity = "insufficient" if dollar_volume < 1_000_000 else "sufficient"
    volume_ratio = median(row.turnover_ratio for row in rows.values())
    volume_state = "volume_spike" if volume_ratio > 2.0 else "normal_volume"
    flags: list[str] = []
    if len(rows) < 2:
        flags.append("insufficient_market_breadth")
    if liquidity == "insufficient":
        flags.append("liquidity_insufficient")
    if any(row.stale_data_flag or row.missing_data_ratio > 0 for row in rows.values()):
        flags.append("market_data_quality_low")
    trade_allowed = not flags
    risk_multiplier = 0.0 if not trade_allowed else 0.5 if volatility == "high_volatility" or trend == "downtrend" else 1.0
    return MarketRegime(
        trend,
        volatility,
        liquidity,
        volume_state,
        breadth,
        None,
        False,
        trade_allowed,
        risk_multiplier,
        tuple(flags),
    )
