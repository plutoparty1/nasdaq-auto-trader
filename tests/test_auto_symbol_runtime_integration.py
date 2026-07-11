import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import nasdaq_auto_trader.automatic_selection_production as automatic_selection
from nasdaq_auto_trader.ai_quant_lab.artifact_paths import (
    StrategyArtifactPaths,
    default_strategy_artifact_paths,
)
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.automatic_selection import (
    AutomaticSelectionRequest,
    prepare_automatic_selection,
)
from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.risk import RiskConfig
from nasdaq_auto_trader.session_claims import SignalKey
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.config_engine_fixtures import compact_strategy_config
from tests.test_auto_symbol_engine import (
    _AcceptedBroker,
    _AutoMarketData,
    _write_paper_strategy,
)


class AutoSymbolRuntimeIntegrationTests(unittest.TestCase):
    def test_invalid_universe_blocks_before_default_client_construction(self):
        client_factory = Mock()
        with patch(
            "nasdaq_auto_trader.quant_data.universe_snapshot.read_quant_resource",
            return_value="{broken",
        ), patch(
            "nasdaq_auto_trader.engine.build_default_client",
            client_factory,
        ):
            engine = TradingEngine(
                AppConfig(
                    mode="dry_run",
                    alpaca=AlpacaCredentials("key", "secret"),
                ),
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                ),
            )

            results = engine.run_once()

        client_factory.assert_not_called()
        self.assertEqual(results, [])
        self.assertEqual(
            engine.last_selection_report.blocked_reasons,
            ("universe_resource_invalid_json",),
        )

    def test_production_selection_reuses_identity_bound_nonlive_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}):
                paths = default_strategy_artifact_paths()
                _write_paper_strategy(paths)
                config = AppConfig(mode="paper", symbols=[])
                now = datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)
                first_market = _AutoMarketData()
                second_market = _AutoMarketData()

                first = automatic_selection.prepare_production_automatic_selection(
                    AutomaticSelectionRequest(config, first_market, paths, now)
                )
                second = automatic_selection.prepare_production_automatic_selection(
                    AutomaticSelectionRequest(config, second_market, paths, now)
                )
                cache_path = (
                    Path(temp_dir)
                    / "NasdaqAutoTrader"
                    / "auto_selection"
                    / "latest.json"
                )

                self.assertEqual(first.report, second.report)
                self.assertTrue(cache_path.exists())
                self.assertLess(
                    len(second_market.bar_requests[0]),
                    len(first_market.bar_requests[0]),
                )

    def test_automatic_engine_persists_state_and_recovers_interrupted_claims(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_paper_strategy(paths)
            store = TradingSessionStore(root / "session.json")
            interrupted = SignalKey(
                market_date="2026-07-10",
                strategy_id="prior",
                strategy_version="v1",
                symbol="AAPL",
                side="buy",
                signal_timestamp="2026-07-10T16:00:00+00:00",
            )
            store.claim(interrupted)
            guard = AutomaticOrderGuard(paths, store, NullAuditLogger())
            settings = TradingSettings(
                auto_symbol_selection_enabled=True,
                max_daily_buy_count=10,
                max_position_qty=10,
            )
            first = TradingEngine(
                AppConfig(
                    mode="dry_run",
                    strategy=compact_strategy_config(),
                    risk=RiskConfig(order_qty=1, max_position_qty=10),
                ),
                broker=_AcceptedBroker(),
                market_data=_AutoMarketData(),
                trading_settings=settings,
                strategy_artifact_paths=paths,
                automatic_order_guard=guard,
            )

            first.run_once()
            reopened_guard = AutomaticOrderGuard(paths, store, NullAuditLogger())
            second = TradingEngine(
                AppConfig(mode="dry_run"),
                broker=_AcceptedBroker(),
                market_data=_AutoMarketData(),
                trading_settings=settings,
                strategy_artifact_paths=paths,
                automatic_order_guard=reopened_guard,
            )
            repeated = store.claim(interrupted)

        self.assertGreaterEqual(second.trading_session_state.buy_count, 1)
        self.assertFalse(repeated.granted)
        self.assertEqual(repeated.reason, "signal_key_uncertain")

    def test_paper_selection_loads_quotes_and_blocks_incomplete_batch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_paper_strategy(paths)
            complete = _AutoMarketData()
            incomplete = _AutoMarketData(missing_quote_symbol="AAPL")
            config = AppConfig(mode="paper", symbols=[])
            now = datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)

            selected = prepare_automatic_selection(
                AutomaticSelectionRequest(config, complete, paths, now)
            )
            blocked = prepare_automatic_selection(
                AutomaticSelectionRequest(config, incomplete, paths, now)
            )

        self.assertEqual(complete.quote_calls, 1)
        self.assertEqual(selected.report.status, "selected")
        self.assertEqual(incomplete.quote_calls, 1)
        self.assertEqual(blocked.report.status, "blocked")


if __name__ == "__main__":
    unittest.main()
