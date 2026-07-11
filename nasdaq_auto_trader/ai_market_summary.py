from __future__ import annotations

from typing import Callable

from .ai_decision_types import MarketSummary
from .config_manager import TradingSettings
from .indicators import atr, rsi, sma
from .models import Bar


def market_summary(bars: list[Bar], settings: TradingSettings) -> MarketSummary:
    if not bars:
        return {"error": "market_data_missing"}
    closes = [bar.close for bar in bars]
    latest = bars[-1]
    previous_close = bars[-2].close if len(bars) >= 2 else latest.open
    change_pct = (
        (latest.close / previous_close - 1) * 100 if previous_close else 0.0
    )
    return {
        "latest_price": round(latest.close, 4),
        "change_pct": round(change_pct, 4),
        "volume": latest.volume,
        "rsi": _safe_round(lambda: rsi(closes, 14), 2),
        "short_ma": _safe_round(lambda: sma(closes, settings.short_ma_period), 4),
        "long_ma": _safe_round(lambda: sma(closes, settings.long_ma_period), 4),
        "volatility_pct": _safe_round(lambda: atr(bars, 14) / latest.close * 100, 4),
    }


def _safe_round(func: Callable[[], float], digits: int) -> float | None:
    try:
        value = func()
    except (ArithmeticError, IndexError, ValueError):
        return None
    return round(float(value), digits)
