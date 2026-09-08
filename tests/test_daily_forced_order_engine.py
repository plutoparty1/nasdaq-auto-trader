import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.automatic_selection import AutomaticSelectionResult
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, Position
from nasdaq_auto_trader.quant_data.symbol_selector import RankedSymbol, SelectionReport
from nasdaq_auto_trader.risk import RiskConfig
from tests.config_engine_fixtures import compact_strategy_config
from tests.test_auto_symbol_engine import (
    AUTO_TEST_NOW,
    _AcceptedBroker,
    _AutoMarketData,
    _guard,
    _rising_bars,
    _write_paper_strategy,
)


class DailyForcedOrderEngineTests(unittest.TestCase):
    def test_normal_sell_decision_runs_before_daily_forced_buy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_paper_strategy(paths, threshold=1.0)
            market = _AutoMarketData(
                positions={"AAPL": Position("AAPL", 1, 200, 240)},
                close_by_symbol={"AAPL": 200},
            )
            engine = TradingEngine(
                AppConfig(
                    mode="dry_run",
                    strategy=compact_strategy_config(),
                    risk=RiskConfig(order_qty=1, max_position_qty=1),
                ),
                broker=_AcceptedBroker(),
                market_data=market,
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                    daily_forced_order_enabled=True,
                    max_daily_buy_count=1,
                    max_daily_sell_count=1,
                ),
                strategy_artifact_paths=paths,
                automatic_order_guard=_guard(paths, root),
                clock=lambda: AUTO_TEST_NOW,
            )

            [result] = engine.run_once()

        self.assertNotIn("daily_forced_order", result)
        self.assertEqual(result["order"].side, "sell")
        self.assertEqual(result["symbol"], "AAPL")

    def test_daily_fallback_does_not_force_sell_manual_holding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_paper_strategy(paths, threshold=1.0)
            selection = AutomaticSelectionResult(
                SelectionReport(
                    status="no_trade",
                    universe_id="nasdaq",
                    universe_effective_date="2026-07-13",
                    strategy_id="auto",
                    strategy_version="v1",
                    strategy_digest="digest",
                    shortlist_count=1,
                    ranked=(RankedSymbol("MSFT", 0.8, 0.8, ("rank_1",)),),
                    selected_symbols=(),
                ),
                {
                    "AAPL": _rising_bars("AAPL", 100),
                    "MSFT": _rising_bars("MSFT", 50),
                },
            )
            engine = TradingEngine(
                AppConfig(
                    mode="dry_run",
                    strategy=compact_strategy_config(),
                    risk=RiskConfig(order_qty=1, max_position_qty=1),
                ),
                broker=_AcceptedBroker(),
                market_data=_AutoMarketData(
                    positions={"AAPL": Position("AAPL", 1, 100, 100)}
                ),
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                    daily_forced_order_enabled=True,
                    max_daily_buy_count=1,
                    max_daily_sell_count=1,
                ),
                strategy_artifact_paths=paths,
                automatic_order_guard=_guard(paths, root),
                clock=lambda: AUTO_TEST_NOW,
            )

            with patch(
                "nasdaq_auto_trader.engine_automatic_cycle.prepare_production_automatic_selection",
                return_value=selection,
            ):
                [result] = engine.run_once()

        self.assertTrue(result["daily_forced_order"])
        self.assertEqual(result["symbol"], "MSFT")
        self.assertEqual(result["order"].side, "buy")

    def test_daily_forced_order_uses_highest_ranked_affordable_symbol(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_paper_strategy(paths, threshold=1.0)
            market = _AutoMarketData(
                account=AccountSnapshot(100, 100, 100),
                close_by_symbol={"AAPL": 500, "MSFT": 50},
            )
            selection = AutomaticSelectionResult(
                SelectionReport(
                    status="no_trade",
                    universe_id="nasdaq",
                    universe_effective_date="2026-07-13",
                    strategy_id="auto",
                    strategy_version="v1",
                    strategy_digest="digest",
                    shortlist_count=2,
                    ranked=(
                        RankedSymbol("AAPL", 0.9, 0.9, ("rank_1",)),
                        RankedSymbol("MSFT", 0.8, 0.8, ("rank_2",)),
                    ),
                    selected_symbols=(),
                ),
                {
                    "AAPL": _rising_bars("AAPL", 500),
                    "MSFT": _rising_bars("MSFT", 50),
                },
                quotes_by_symbol={
                    "AAPL": (499.0, 500.0),
                    "MSFT": (50.0, 51.0),
                },
            )
            engine = TradingEngine(
                AppConfig(
                    mode="dry_run",
                    strategy=compact_strategy_config(),
                    risk=RiskConfig(order_qty=1, max_position_qty=1),
                ),
                broker=_AcceptedBroker(),
                market_data=market,
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                    daily_forced_order_enabled=True,
                    max_daily_buy_count=1,
                    max_daily_sell_count=1,
                ),
                strategy_artifact_paths=paths,
                automatic_order_guard=_guard(paths, root),
                clock=lambda: AUTO_TEST_NOW,
            )

            with patch(
                "nasdaq_auto_trader.engine_automatic_cycle.prepare_production_automatic_selection",
                return_value=selection,
            ):
                [result] = engine.run_once()

        self.assertEqual(engine.last_selection_report.status, "no_trade")
        self.assertTrue(result["daily_forced_order"])
        self.assertEqual(result["symbol"], "MSFT")
        self.assertEqual(result["order"].side, "buy")
        self.assertEqual(result["order"].qty, 1)
        self.assertEqual(result["order"].limit_price, 51.0)

    def test_daily_forced_order_runs_only_when_daily_order_count_is_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_paper_strategy(paths, threshold=1.0)
            engine = TradingEngine(
                AppConfig(
                    mode="dry_run",
                    strategy=compact_strategy_config(),
                    risk=RiskConfig(order_qty=1, max_position_qty=1),
                ),
                broker=_AcceptedBroker(),
                market_data=_AutoMarketData(),
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                    daily_forced_order_enabled=True,
                    max_daily_buy_count=1,
                    max_daily_sell_count=1,
                ),
                strategy_artifact_paths=paths,
                automatic_order_guard=_guard(paths, root),
                clock=lambda: AUTO_TEST_NOW,
            )

            first = engine.run_once()
            second = engine.run_once()

        self.assertTrue(first[0]["daily_forced_order"])
        self.assertFalse(any(item.get("daily_forced_order") for item in second))
