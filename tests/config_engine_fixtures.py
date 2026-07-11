import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nasdaq_auto_trader.backtest import Backtester
from nasdaq_auto_trader.broker import AlpacaCredentials, KISClient, KISCredentials
import nasdaq_auto_trader.cli as cli_module
from nasdaq_auto_trader.cli import main
from nasdaq_auto_trader.config import AppConfig, load_config, validate_trading_mode
from nasdaq_auto_trader.config_manager import (
    TradingSessionState,
    TradingSettings,
    apply_settings_to_app_config,
)
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.market_hours import regular_market_session
from nasdaq_auto_trader.models import AccountSnapshot, Bar, OrderRequest, Position
from nasdaq_auto_trader.risk import RiskConfig, RiskManager
from nasdaq_auto_trader.strategy import StrategyConfig, TechnicalStrategy


def compact_strategy_config(**overrides):
    defaults = {
        "sma_fast": 5,
        "sma_slow": 20,
        "ema_fast": 6,
        "ema_slow": 13,
        "rsi_period": 14,
        "macd_fast": 6,
        "macd_slow": 13,
        "macd_signal": 5,
        "bollinger_period": 20,
        "long_sma": 30,
        "momentum_period": 10,
        "donchian_period": 20,
        "stochastic_period": 14,
        "volume_period": 20,
        "atr_period": 14,
        "buy_score": 5,
        "sell_score": 4,
    }
    defaults.update(overrides)
    return StrategyConfig(**defaults)


class FakeBroker:
    def __init__(self):
        self.orders = []

    def submit_order(self, order):
        self.orders.append(order)
        return {"status": "fake_submitted"}


class FakeMarketData:
    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        bars = []
        for index in range(70):
            close = 100 + index
            bars.append(
                Bar(
                    symbol="QQQ",
                    timestamp=f"T{index + 1:03d}",
                    open=close - 0.5,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=1_000_000 + index,
                )
            )
        return {"QQQ": bars}
