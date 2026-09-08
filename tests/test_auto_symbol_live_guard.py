import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.live_authorization import (
    LiveAuthorizationBlock,
    LiveAuthorizationRequest,
    create_live_authorization,
)
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.auto_symbol_live_guard_fixtures import (
    _LiveBroker,
    _LiveMarketData,
    _LiveSellMarketData,
    _SecondWriteFailsAudit,
    _live_engine,
    _write_champion,
)


class AutoSymbolLiveGuardTests(unittest.TestCase):
    def test_daily_unattended_mode_authorizes_the_first_normal_order(self):
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
            engine = _live_engine(
                paths,
                guard,
                broker,
                issue_authorization=False,
                daily_forced=True,
            )

            results = engine.run_once()
            stored = guard.authorization_store.load()

        self.assertEqual(len(broker.orders), 1)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].get("daily_forced_order", False))
        self.assertIsNotNone(stored)
        self.assertEqual(stored.envelope.market_date.isoformat(), "2026-07-13")
        self.assertEqual(stored.envelope.max_attempts, 0)
        self.assertEqual(stored.envelope.purpose, "automatic")

    def test_normal_order_continues_when_daily_fallback_is_not_due(self):
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
            engine = _live_engine(
                paths,
                guard,
                broker,
                issue_authorization=False,
                daily_forced=True,
            )
            engine.trading_session_state.buy_count = 1

            engine.run_once()
            stored = guard.authorization_store.load()

        self.assertEqual(len(broker.orders), 1)
        self.assertEqual(stored.envelope.purpose, "automatic")
        self.assertEqual(stored.envelope.max_attempts, 0)

    def test_daily_fallback_authorization_is_replaced_for_normal_order(self):
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
            engine = _live_engine(
                paths,
                guard,
                broker,
                issue_authorization=False,
                daily_forced=True,
            )
            created = create_live_authorization(
                LiveAuthorizationRequest(
                    engine.config,
                    paths,
                    engine._clock(),
                    max_attempts=12,
                    purpose="daily_forced",
                )
            )
            if isinstance(created, LiveAuthorizationBlock):
                raise AssertionError(created.reason)
            guard.authorization_store.issue(created)
            engine.trading_session_state.buy_count = 1

            results = engine.run_once()
            stored = guard.authorization_store.load()

        self.assertEqual(len(broker.orders), 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(stored.envelope.purpose, "automatic")
        self.assertEqual(stored.envelope.max_attempts, 0)

    def test_daily_authorization_allows_normal_sell_before_fallback(self):
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
            engine = _live_engine(
                paths,
                guard,
                broker,
                issue_authorization=False,
                daily_forced=True,
                market_data=_LiveSellMarketData(),
            )

            results = engine.run_once()

        self.assertTrue(
            any(order.symbol == "AAPL" and order.side == "sell" for order in broker.orders)
        )
        self.assertFalse(any(item.get("daily_forced_order") for item in results))

    def test_daily_fallback_replaces_same_day_automatic_authorization(self):
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
            engine = _live_engine(paths, guard, broker, daily_forced=True)
            original = guard.authorization_store.load()
            if original is None:
                raise AssertionError("automatic authorization was not issued")

            results = engine.run_once()
            stored = guard.authorization_store.load()

        self.assertEqual(len(broker.orders), 1)
        self.assertTrue(results[0]["daily_forced_order"])
        self.assertIsNotNone(stored)
        self.assertNotEqual(
            stored.envelope.authorization_id,
            original.envelope.authorization_id,
        )
        self.assertEqual(stored.envelope.purpose, "daily_forced")
        self.assertEqual(stored.envelope.max_attempts, 1)

    def test_revoked_session_is_not_automatically_reissued(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_champion(paths)
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(root / "session.json"),
                NullAuditLogger(),
            )
            guard.authorization_store.clear(archive=True)
            broker = _LiveBroker("accepted")
            engine = _live_engine(
                paths,
                guard,
                broker,
                issue_authorization=False,
                daily_forced=True,
            )

            results = engine.run_once()

        self.assertEqual(results, [])
        self.assertEqual(broker.orders, [])
        self.assertIsNone(guard.authorization_store.load())

    def test_two_stale_engines_cannot_submit_two_daily_fallback_orders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_champion(paths, threshold=1.0)
            session_path = root / "session.json"
            first_guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(session_path),
                NullAuditLogger(),
            )
            second_guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(session_path),
                NullAuditLogger(),
            )
            first_broker = _LiveBroker("accepted")
            second_broker = _LiveBroker("accepted")
            first_engine = _live_engine(
                paths,
                first_guard,
                first_broker,
                max_attempts=12,
                issue_authorization=False,
                daily_forced=True,
            )
            second_engine = _live_engine(
                paths,
                second_guard,
                second_broker,
                max_attempts=12,
                issue_authorization=False,
                daily_forced=True,
            )
            authorization = create_live_authorization(
                LiveAuthorizationRequest(
                    first_engine.config,
                    paths,
                    first_engine._clock(),
                    max_attempts=12,
                    purpose="daily_forced",
                )
            )
            if isinstance(authorization, LiveAuthorizationBlock):
                raise AssertionError(authorization.reason)
            first_guard.authorization_store.issue(authorization)

            first_results = first_engine.run_once()
            second_results = second_engine.run_once()

        self.assertEqual(len(first_broker.orders), 1)
        self.assertTrue(first_results[0]["daily_forced_order"])
        self.assertEqual(second_broker.orders, [])
        self.assertEqual(
            second_results[0]["response"]["reason"],
            "learned_daily_order_limit_reached",
        )

if __name__ == "__main__":
    unittest.main()
