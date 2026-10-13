from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .config import AppConfig
from .engine_types import MarketDataLike
from .learning_history import LearningHistoryWindow, collect_learning_history
from .market_hours import NASDAQ
from .quant_data.features import PriceBar


def collect_completed_learning_bars(
    config: AppConfig,
    market_data: MarketDataLike,
    now: datetime,
) -> dict[str, list[PriceBar]]:
    normalized = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    schedule = NASDAQ.schedule(
        start_date=(normalized - timedelta(days=14)).date(),
        end_date=normalized.date(),
    )
    completed = schedule[schedule["market_close"] <= normalized]
    if completed.empty:
        return {}
    end_date = datetime.fromisoformat(str(completed.index[-1])).date()
    start_date = end_date - timedelta(days=max(config.lookback_days * 2, 730))
    raw = collect_learning_history(
        market_data, list(config.symbols),
        LearningHistoryWindow(config.timeframe, start_date, end_date, max(config.bar_limit, 320)),
    )
    return {
        symbol: [
            PriceBar(
                symbol=bar.symbol,
                timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in raw.get(symbol, [])
        ]
        for symbol in config.symbols
    }
