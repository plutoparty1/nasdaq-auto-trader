import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSessionState, TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import Position
from tests.config_engine_fixtures import compact_strategy_config
from tests.test_auto_symbol_engine import (
    AUTO_TEST_NOW,
    _AcceptedBroker,
    _AutoMarketData,
    _guard,
)


class AutoSymbolProfitProtectionTests(unittest.TestCase):
    def test_protective_exit_runs_before_entry_strategy_resolution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            market = _AutoMarketData(
                positions={"HELD": Position("HELD", 1, 101.5, 100)},
                close_by_symbol={"HELD": 101.5},
            )
            state = TradingSessionState()
            state.observe_position(
                "HELD",
                Position("HELD", 1, 103, 100),
                AUTO_TEST_NOW,
            )
            engine = TradingEngine(
                AppConfig(
                    mode="dry_run",
                    symbols=["POISON"],
                    strategy=compact_strategy_config(
                        stop_loss_pct=0.5,
                        take_profit_pct=0.05,
                        sell_score=999,
                        trailing_stop_enabled=True,
                        trailing_stop_activation_pct=0.02,
                        trailing_stop_pct=0.01,
                    ),
                ),
                broker=_AcceptedBroker(),
                market_data=market,
                trading_settings=TradingSettings(auto_symbol_selection_enabled=True),
                trading_session_state=state,
                strategy_artifact_paths=paths,
                automatic_order_guard=_guard(paths, Path(temp_dir)),
                clock=lambda: AUTO_TEST_NOW,
            )

            [result] = engine.run_once()

        self.assertEqual(result["decision"].reasons, ["trailing_profit_protection"])
        self.assertEqual(result["order"].side, "sell")
        self.assertEqual(result["response"]["status"], "dry_run")
