import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import Position
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.config_engine_fixtures import compact_strategy_config
from tests.test_auto_symbol_live_guard import (
    _LiveBroker,
    _LiveMarketData,
    _write_champion,
)


class AutoSymbolLiveExitGuardTests(unittest.TestCase):
    def test_held_sell_without_signal_bar_cannot_bypass_automatic_guard(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_champion(paths)
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(root / "session.json"),
                NullAuditLogger(),
            )
            broker = _LiveBroker("accepted")
            now = datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)
            engine = TradingEngine(
                AppConfig(
                    mode="live",
                    allow_live_trading=True,
                    symbols=["POISON"],
                    alpaca=AlpacaCredentials("key", "secret", paper=False),
                    strategy=compact_strategy_config(),
                ),
                broker=broker,
                market_data=_HeldWithoutBarsMarketData(),
                clock=lambda: now,
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                    dry_run=False,
                    live_trading=True,
                    require_confirm_before_buy=False,
                    require_confirm_before_sell=False,
                    time_based_sell_enabled=True,
                    max_holding_minutes=1,
                    max_daily_buy_count=10,
                    max_daily_sell_count=10,
                    max_position_qty=10,
                ),
                live_order_confirmation=True,
                strategy_artifact_paths=paths,
                automatic_order_guard=guard,
            )
            engine.trading_session_state.position_first_seen_at["HELD"] = (
                now - timedelta(minutes=10)
            )

            results = engine.run_once()

        self.assertFalse(any(order.symbol == "HELD" for order in broker.orders))
        self.assertTrue(
            any(
                item["symbol"] == "HELD"
                and item["response"]["reason"]
                == "automatic_signal_timestamp_missing"
                for item in results
            )
        )


class _HeldWithoutBarsMarketData(_LiveMarketData):
    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        loaded = super().get_stock_bars(symbols, timeframe, start, end, limit)
        loaded.pop("HELD", None)
        return loaded

    def list_positions(self, refresh=False):
        del refresh
        return {"HELD": Position("HELD", 1, 100, 100)}


if __name__ == "__main__":
    unittest.main()
