import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.automatic_risk import AutomaticRiskLimits
from nasdaq_auto_trader.automatic_selection import AutomaticSelectionResult
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.quant_data.symbol_selector import RankedSymbol, SelectionReport
from nasdaq_auto_trader.risk import RiskConfig
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.auto_symbol_live_guard_fixtures import (
    _LiveBroker,
    _live_engine,
    _write_champion,
)
from tests.config_engine_fixtures import compact_strategy_config
from tests.test_auto_symbol_engine import (
    AUTO_TEST_NOW,
    _AcceptedBroker,
    _AutoMarketData,
    _guard,
    _rising_bars,
)


class DailyOrderMinimumWithoutMaximumTests(unittest.TestCase):
    def test_daily_forced_order_buys_cash_affordable_share_despite_exposure_cap(self):
        # Given: the production-sized account and learned 50% exposure limits.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_champion(paths, threshold=1.0)
            market = _AutoMarketData(
                account=AccountSnapshot(38.21, 38.21, 38.21),
                close_by_symbol={"WMT": 115.82, "WBD": 27.70},
            )
            selection = AutomaticSelectionResult(
                SelectionReport(
                    status="no_trade",
                    universe_id="nasdaq",
                    universe_effective_date="2026-08-12",
                    strategy_id="auto",
                    strategy_version="v1",
                    strategy_digest="digest",
                    shortlist_count=2,
                    ranked=(),
                    selected_symbols=(),
                ),
                {
                    "WMT": _rising_bars("WMT", 115.82),
                    "WBD": _rising_bars("WBD", 27.70),
                },
                AutomaticRiskLimits(0.5, 0.5, 35.0, 0, 0.01, 0.02),
                quotes_by_symbol={
                    "WMT": (115.52, 115.82),
                    "WBD": (27.56, 27.70),
                },
                prethreshold_ranked=(
                    RankedSymbol("WMT", 0.99, 0.99, ("rank_1",)),
                    RankedSymbol("WBD", 0.98, 0.98, ("rank_2",)),
                ),
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
                    max_daily_buy_count=0,
                    max_daily_sell_count=0,
                ),
                strategy_artifact_paths=paths,
                automatic_order_guard=_guard(paths, root),
                clock=lambda: AUTO_TEST_NOW,
            )

            # When: the daily minimum fallback runs with no prior order.
            with patch(
                "nasdaq_auto_trader.engine_automatic_cycle.prepare_production_automatic_selection",
                return_value=selection,
            ):
                [result] = engine.run_once()

        # Then: the highest-ranked cash-affordable whole share is ordered.
        self.assertTrue(result["daily_forced_order"])
        self.assertEqual(result["symbol"], "WBD")
        self.assertEqual(result["order"].side, "buy")
        self.assertEqual(result["order"].qty, 1)
        self.assertEqual(result["order"].limit_price, 27.70)
        self.assertEqual(result["response"]["status"], "dry_run")

    def test_daily_fallback_does_not_cap_later_normal_orders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_champion(paths, threshold=1.0)
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(root / "session.json"),
                NullAuditLogger(),
            )
            broker = _LiveBroker("accepted")
            engine = _live_engine(
                paths,
                guard,
                broker,
                issue_authorization=False,
                daily_forced=True,
            )

            first_results = engine.run_once()
            _write_champion(paths, strategy_id="next")
            second_results = engine.run_once()
            stored = guard.authorization_store.load()

        self.assertTrue(first_results[0]["daily_forced_order"])
        self.assertEqual(len(broker.orders), 2)
        self.assertFalse(second_results[0].get("daily_forced_order", False))
        self.assertEqual(stored.envelope.purpose, "automatic")
        self.assertEqual(stored.envelope.max_attempts, 0)


if __name__ == "__main__":
    unittest.main()
