import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import (
    AuditEvent,
    AuditLogger,
    NullAuditLogger,
)
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.models import Position
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.auto_symbol_live_guard_fixtures import (
    _LiveBroker,
    _LiveMarketData,
    _bars,
    _SecondWriteFailsAudit,
    _live_engine,
    _write_champion,
)


class AutoSymbolLiveAuditTests(unittest.TestCase):
    def test_new_five_minute_cycle_can_buy_again_after_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                NullAuditLogger(),
            )
            broker = _LiveBroker("accepted")
            market = _LiveMarketData()
            market.get_stock_bars = lambda symbols, *_args, **_kwargs: {
                symbol: [
                    replace(bar, timestamp="20260713")
                    for bar in _bars(symbol)
                ]
                for symbol in symbols
            }
            engine = _live_engine(paths, guard, broker, market_data=market)
            assert engine.trading_settings is not None
            engine.trading_settings = replace(
                engine.trading_settings,
                unattended_interval_minutes=5,
                max_daily_buy_count=2,
            )

            engine._clock = lambda: datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)
            engine.run_once()
            bought_symbol = broker.orders[-1].symbol
            engine._clock = lambda: datetime(2026, 7, 13, 14, 34, tzinfo=timezone.utc)
            same_cycle = engine.run_once()
            market.list_positions = lambda refresh=False: {
                bought_symbol: Position(bought_symbol, 1, 239, 100)
            }
            engine._clock = lambda: datetime(2026, 7, 13, 14, 35, tzinfo=timezone.utc)
            engine.run_once()
            market.list_positions = lambda refresh=False: {}
            engine._clock = lambda: datetime(2026, 7, 13, 14, 40, tzinfo=timezone.utc)
            third = engine.run_once()
            safety = guard.session_store.load_safety_state()

        self.assertEqual([order.side for order in broker.orders], ["buy", "sell", "buy"])
        self.assertEqual((safety.buy_count, safety.sell_count), (2, 1))
        self.assertTrue(
            any(
                item.get("response", {}).get("reason") == "signal_key_submitted"
                for item in same_cycle
            )
        )
        self.assertFalse(
            any(
                item.get("response", {}).get("reason") == "signal_key_submitted"
                for item in third
            )
        )

    def test_real_audit_logger_fails_while_cross_process_lock_is_held(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "audit.jsonl"
            lock_owner = TradingSessionStore(path, lock_timeout_seconds=0.01)
            logger = AuditLogger(path)
            logger.lock_timeout_seconds = 0.01

            with lock_owner._locked():
                written = logger.append(AuditEvent("test_event"))

        self.assertFalse(written)

    def test_outcome_audit_failure_marks_claim_uncertain(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            audit = _SecondWriteFailsAudit()
            store = TradingSessionStore(Path(temp_dir) / "session.json")
            guard = AutomaticOrderGuard(paths, store, audit)
            broker = _LiveBroker("accepted")
            engine = _live_engine(paths, guard, broker)

            results = engine.run_once()

        self.assertEqual(len(broker.orders), 1)
        self.assertTrue(
            any(
                item["response"]["reason"]
                == "order_outcome_audit_failed_reconcile_required"
                for item in results
            )
        )

    def test_settings_block_emits_decision_audit_without_intent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            audit = NullAuditLogger()
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                audit,
            )
            engine = _live_engine(paths, guard, _LiveBroker("accepted"))
            engine.trading_session_state.buy_count = 10

            results = engine.run_once()

        self.assertTrue(
            any(
                item["response"]["reason"] == "max_daily_buy_count_reached"
                for item in results
            )
        )
        self.assertEqual(
            [event.event_type for event in audit.events],
            ["automatic_order_blocked"],
        )

    def test_live_confirmation_blocks_champion_change_during_same_engine(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths, "alpha")
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                NullAuditLogger(),
            )
            broker = _LiveBroker("accepted")
            engine = _live_engine(paths, guard, broker)

            first = engine.run_once()
            _write_champion(paths, "beta")
            second = engine.run_once()

        self.assertGreater(len(first), 0)
        self.assertEqual(len(broker.orders), 1)
        self.assertTrue(
            any(
                item["response"]["reason"]
                == "live_authorization_binding_changed"
                for item in second
            )
        )

    def test_live_intent_audit_failure_blocks_before_broker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            audit = NullAuditLogger()
            audit.fail_writes = True
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                audit,
            )
            broker = _LiveBroker("accepted")
            engine = _live_engine(paths, guard, broker)

            results = engine.run_once()
            stored = guard.authorization_store.load()

        self.assertEqual(broker.orders, [])
        self.assertTrue(
            any(
                item["response"]["reason"] == "audit_log_write_failed"
                for item in results
            )
        )
        self.assertEqual(stored.attempts, 1)

    def test_same_rejected_signal_key_does_not_reach_broker_twice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            audit = NullAuditLogger()
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                audit,
            )
            broker = _LiveBroker("rejected")
            engine = _live_engine(paths, guard, broker)

            first = engine.run_once()
            second = engine.run_once()

        self.assertGreater(len(first), 0)
        self.assertGreater(len(second), 0)
        self.assertEqual(len(broker.orders), 1)
        self.assertTrue(
            any(
                item["response"]["reason"] == "signal_key_rejected"
                for item in second
            )
        )

    def test_fresh_rollback_blocks_cached_champion_before_broker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            audit = NullAuditLogger()
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                audit,
            )
            broker = _LiveBroker("accepted")
            engine = _live_engine(paths, guard, broker)
            original_submit = guard.begin

            def rollback_before_begin(context, order, now):
                paths.promoted_path.write_text(
                    json.dumps({"status": "rollback", "mode": "no_trade"}),
                    encoding="utf-8",
                )
                return original_submit(context, order, now)

            guard.begin = rollback_before_begin

            results = engine.run_once()

        self.assertEqual(broker.orders, [])
        self.assertTrue(
            any(
                item["response"]["reason"] == "promoted_strategy_rollback"
                for item in results
            )
        )
