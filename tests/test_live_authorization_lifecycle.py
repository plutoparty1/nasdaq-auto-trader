import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import OrderRequest
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.config_engine_fixtures import compact_strategy_config
from tests.test_auto_symbol_live_guard import (
    _LiveBroker,
    _LiveMarketData,
    _live_engine,
    _write_champion,
)


class LiveAuthorizationLifecycleTests(unittest.TestCase):
    def test_unattended_fixed_symbol_live_requires_approved_automatic_strategy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            broker = _LiveBroker("accepted")
            engine = TradingEngine(
                AppConfig(
                    mode="live",
                    allow_live_trading=True,
                    live_environment_authorized=True,
                    symbols=["POISON"],
                    alpaca=AlpacaCredentials("key", "secret", paper=False),
                    strategy=compact_strategy_config(),
                ),
                broker=broker,
                market_data=_LiveMarketData(),
                clock=lambda: datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc),
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=False,
                    unattended_operation_enabled=True,
                    dry_run=False,
                    live_trading=True,
                    require_confirm_before_buy=False,
                    require_confirm_before_sell=False,
                ),
                live_order_confirmation=True,
                strategy_artifact_paths=paths,
            )

            response = engine._submit_or_block_order(
                OrderRequest("POISON", "buy", qty=1, limit_price=10),
            )

        self.assertEqual(response["status"], "blocked")
        self.assertEqual(
            response["reason"],
            "unattended_live_requires_approved_strategy",
        )
        self.assertTrue(response["terminal"])
        self.assertEqual(broker.orders, [])

    def test_new_engine_cannot_reset_live_authorization_cycle_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                NullAuditLogger(),
            )
            broker = _LiveBroker("accepted")
            first_engine = _live_engine(paths, guard, broker, max_cycles=1)
            second_engine = _live_engine(paths, guard, broker, max_cycles=1)

            first = first_engine.run_once()
            second = second_engine.run_once()

        self.assertGreater(len(first), 0)
        self.assertEqual(second, [])
        self.assertEqual(len(broker.orders), 1)
        self.assertEqual(
            second_engine.last_selection_report.blocked_reasons,
            ("live_authorization_cycle_limit_reached",),
        )

    def test_new_process_guard_cannot_reset_live_authorization_cycle_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            session_path = Path(temp_dir) / "session.json"
            broker = _LiveBroker("accepted")
            first_guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(session_path),
                NullAuditLogger(),
            )
            first_engine = _live_engine(paths, first_guard, broker, max_cycles=1)
            first = first_engine.run_once()

            restarted_guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(session_path),
                NullAuditLogger(),
            )
            restarted_engine = _live_engine(
                paths,
                restarted_guard,
                broker,
                max_cycles=1,
            )
            restarted = restarted_engine.run_once()

        self.assertGreater(len(first), 0)
        self.assertEqual(restarted, [])
        self.assertEqual(len(broker.orders), 1)
        self.assertEqual(
            restarted_engine.last_selection_report.blocked_reasons,
            ("live_authorization_cycle_limit_reached",),
        )

    def test_explicit_authorization_reset_allows_a_new_bounded_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            session_path = Path(temp_dir) / "session.json"
            broker = _LiveBroker("accepted")
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(session_path),
                NullAuditLogger(),
            )
            first_engine = _live_engine(paths, guard, broker, max_cycles=1)
            first_engine.run_once()

            reset_reason = guard.reset_live_authorization()
            renewed_engine = _live_engine(paths, guard, broker, max_cycles=1)
            renewed_engine.run_once()

        self.assertEqual(reset_reason, "")
        self.assertEqual(renewed_engine.last_selection_report.status, "selected")


if __name__ == "__main__":
    unittest.main()
