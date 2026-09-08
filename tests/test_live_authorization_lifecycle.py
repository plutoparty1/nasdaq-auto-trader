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
    def test_after_close_cycle_keeps_selection_without_consuming_attempt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                NullAuditLogger(),
            )
            broker = _LiveBroker("accepted")
            engine = _live_engine(paths, guard, broker)
            engine._clock = lambda: datetime(
                2026,
                7,
                13,
                20,
                1,
                tzinfo=timezone.utc,
            )

            results = engine.run_once()
            stored = guard.authorization_store.load()

        self.assertEqual(engine.last_selection_report.status, "selected")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["response"]["reason"], "regular_market_closed")
        self.assertEqual(stored.attempts, 0)
        self.assertEqual(broker.orders, [])

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
            first_engine = _live_engine(paths, guard, broker, max_attempts=1)
            second_engine = _live_engine(paths, guard, broker, max_attempts=1)

            first = first_engine.run_once()
            second = second_engine.run_once()

        self.assertGreater(len(first), 0)
        self.assertGreater(len(second), 0)
        self.assertEqual(len(broker.orders), 1)
        self.assertEqual(
            second[0]["response"]["reason"],
            "live_authorization_attempt_limit_reached",
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
            first_engine = _live_engine(paths, first_guard, broker, max_attempts=1)
            first = first_engine.run_once()
            stored = first_guard.authorization_store.load()
            self.assertIsNotNone(stored)

            restarted_guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(session_path),
                NullAuditLogger(),
                broker_authorization_digest=(
                    stored.envelope.broker_authorization_digest
                ),
            )
            restart_reason = restarted_guard.start_cycle(
                datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)
            )

        self.assertGreater(len(first), 0)
        self.assertEqual(len(broker.orders), 1)
        self.assertEqual(restart_reason, "")
        self.assertEqual(restarted_guard.authorization_attempts, 1)

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
            first_engine = _live_engine(paths, guard, broker, max_attempts=1)
            first_engine.run_once()

            reset_reason = guard.reset_live_authorization()
            renewed_engine = _live_engine(paths, guard, broker, max_attempts=1)
            renewed_engine.run_once()

        self.assertEqual(reset_reason, "")
        self.assertEqual(renewed_engine.last_selection_report.status, "selected")


if __name__ == "__main__":
    unittest.main()
