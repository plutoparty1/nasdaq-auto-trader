from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math

from .features import PriceBar


MIN_HISTORY_BARS = 20
MAX_SPREAD_BPS = 100.0
MIN_AVERAGE_DOLLAR_VOLUME = 100_000.0
MAX_MARKET_DATA_AGE = timedelta(days=7)
MAX_DAILY_RETURN = 0.25


@dataclass(frozen=True, slots=True)
class MarketQualityResult:
    symbols: tuple[str, ...]
    rejected: dict[str, tuple[str, ...]]


def filter_tradeable_symbols(
    bars_by_symbol: dict[str, list[PriceBar]],
    *,
    now: datetime | None = None,
    quotes_required: bool = False,
) -> MarketQualityResult:
    accepted: list[str] = []
    rejected: dict[str, tuple[str, ...]] = {}
    for symbol in sorted(bars_by_symbol):
        reasons = _quality_reasons(
            bars_by_symbol[symbol],
            now=now,
            quotes_required=quotes_required,
        )
        if reasons:
            rejected[symbol] = reasons
        else:
            accepted.append(symbol)
    return MarketQualityResult(tuple(accepted), rejected)


def _quality_reasons(
    bars: list[PriceBar],
    *,
    now: datetime | None,
    quotes_required: bool,
) -> tuple[str, ...]:
    if len(bars) < MIN_HISTORY_BARS:
        return ("insufficient_bar_history",)
    latest = bars[-1]
    reasons: list[str] = []
    recent = bars[-MIN_HISTORY_BARS:]
    if any(not _finite_bar(item) for item in bars):
        return ("market_data_non_finite",)
    if any(not _valid_ohlcv(item) for item in bars):
        reasons.append("market_data_ohlcv_invalid")
    if latest.close <= 0:
        reasons.append("non_positive_price")
    if sum(item.volume for item in recent) <= 0:
        reasons.append("insufficient_volume")
    average_dollar_volume = sum(
        item.close * item.volume for item in recent
    ) / MIN_HISTORY_BARS
    if average_dollar_volume < MIN_AVERAGE_DOLLAR_VOLUME:
        reasons.append("insufficient_dollar_volume")
    if quotes_required and not _quote_available(latest):
        reasons.append("quote_unavailable")
    spread = _spread_bps(latest)
    if spread > MAX_SPREAD_BPS:
        reasons.append("abnormal_spread")
    if now is not None and _is_stale(latest.timestamp, now):
        reasons.append("stale_market_data")
    if _is_outlier(bars):
        reasons.append("price_outlier")
    return tuple(reasons)


def _spread_bps(bar: PriceBar) -> float:
    if bar.bid <= 0 or bar.ask <= 0 or bar.ask < bar.bid:
        return 0.0
    midpoint = (bar.bid + bar.ask) / 2
    return ((bar.ask - bar.bid) / midpoint) * 10_000


def _quote_available(bar: PriceBar) -> bool:
    return bar.bid > 0 and bar.ask >= bar.bid


def _is_stale(timestamp: str, now: datetime) -> bool:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    effective_now = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    age = effective_now.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)
    return age < timedelta(0) or age > MAX_MARKET_DATA_AGE


def _is_outlier(bars: list[PriceBar]) -> bool:
    previous = bars[-2].close
    if previous <= 0:
        return True
    return abs((bars[-1].close / previous) - 1) > MAX_DAILY_RETURN


def _finite_bar(bar: PriceBar) -> bool:
    return all(
        math.isfinite(value)
        for value in (
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
            bar.bid,
            bar.ask,
        )
    )


def _valid_ohlcv(bar: PriceBar) -> bool:
    return (
        bar.open > 0
        and bar.close > 0
        and bar.volume >= 0
        and bar.low > 0
        and bar.high >= max(bar.open, bar.close, bar.low)
        and bar.low <= min(bar.open, bar.close, bar.high)
    )
