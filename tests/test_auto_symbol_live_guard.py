import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import (
    AuditEvent,
    AuditLogger,
    NullAuditLogger,
)
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, Bar
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.ai_quant_fixtures import promoted_payload, valid_spec_payload
from tests.config_engine_fixtures import compact_strategy_config


class AutoSymbolLiveGuardTests(unittest.TestCase):
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
            any(item["response"]["reason"] == "max_daily_buy_count_reached" for item in results)
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

        self.assertEqual(broker.orders, [])
        self.assertTrue(any(item["response"]["reason"] == "audit_log_write_failed" for item in results))

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
        self.assertTrue(any(item["response"]["reason"] == "signal_key_rejected" for item in second))

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
        self.assertTrue(any(item["response"]["reason"] == "promoted_strategy_rollback" for item in results))


def _live_engine(paths, guard, broker):
    now = datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)
    return TradingEngine(
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
        clock=lambda: now,
        trading_settings=TradingSettings(
            auto_symbol_selection_enabled=True,
            dry_run=False,
            live_trading=True,
            require_confirm_before_buy=False,
            require_confirm_before_sell=False,
            max_daily_buy_count=10,
            max_position_qty=10,
        ),
        live_order_confirmation=True,
        strategy_artifact_paths=paths,
        automatic_order_guard=guard,
    )


class _LiveMarketData:
    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        del timeframe, start, end, limit
        return {symbol: _bars(symbol) for symbol in symbols}

    def get_latest_quotes(self, symbols):
        return {symbol: {"bp": 238.99, "ap": 239.01} for symbol in symbols}

    def get_account(self, refresh=False):
        del refresh
        return AccountSnapshot(10_000, 10_000, 10_000)

    def list_positions(self, refresh=False):
        del refresh
        return {}


class _LiveBroker:
    def __init__(self, status: str) -> None:
        self.status = status
        self.orders = []

    def submit_order(self, order):
        self.orders.append(order)
        return {"status": self.status, "id": str(len(self.orders))}


class _SecondWriteFailsAudit:
    def __init__(self) -> None:
        self.calls = 0

    def append(self, event):
        del event
        self.calls += 1
        return self.calls == 1


def _bars(symbol: str) -> list[Bar]:
    return [
        Bar(
            symbol,
            "2026-07-13T14:29:00+00:00",
            99 + index,
            101 + index,
            98 + index,
            100 + index,
            1_000_000,
        )
        for index in range(140)
    ]


def _write_champion(paths: StrategyArtifactPaths, strategy_id: str = "auto") -> None:
    payload = valid_spec_payload()
    payload["strategy_id"] = strategy_id
    payload["entry_rule"]["top_n"] = 1
    paths.spec_dir.mkdir(parents=True, exist_ok=True)
    (paths.spec_dir / f"{strategy_id}-v1.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    promoted = promoted_payload(strategy_id)
    paths.promoted_path.write_text(json.dumps(promoted), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
