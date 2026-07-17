import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nasdaq_auto_trader.broker import BrokerRequestError
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import (
    TradingSessionState,
    TradingSettings,
    validate_order_against_settings,
)
from nasdaq_auto_trader.learning_runner import LearningRunResult
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest, Position
from nasdaq_auto_trader.operating_state import OperatingStateStore
from nasdaq_auto_trader.session_claims import SignalKey
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.app_controller_fixtures import IsolatedControllerTestCase


class AmbiguousOrderFactory:
    def __call__(self, config, **kwargs):
        del config, kwargs

        def fail():
            raise BrokerRequestError("response lost after submission")

        return SimpleNamespace(run_once=fail)


class TerminalOrderResponseFactory:
    def __call__(self, config, **kwargs):
        del config, kwargs
        return SimpleNamespace(
            run_once=lambda: [
                {
                    "symbol": "QQQ",
                    "response": {
                        "status": "blocked",
                        "reason": "order_outcome_audit_failed_reconcile_required",
                        "terminal": True,
                        "broker_submitted": True,
                    },
                }
            ]
        )


class UnattendedOrderSafetyTests(IsolatedControllerTestCase):
    def test_ambiguous_order_outcome_pauses_unattended_scheduler(self):
        controller = self.create_controller(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            engine_factory=AmbiguousOrderFactory(),
            trading_settings=TradingSettings(
                unattended_operation_enabled=True,
                stop_on_order_error=False,
            ),
            session_store=self.session_store(),
        )
        controller.start(interval_seconds=60)

        with self.assertRaises(BrokerRequestError):
            controller.run_auto_cycle(force=True)

        self.assertEqual(controller.state, "paused")
        self.assertIsNone(controller.next_run_at)
        self.assertEqual(controller.last_error, "response lost after submission")

    def test_terminal_order_response_pauses_unattended_scheduler(self):
        controller = self.create_controller(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            engine_factory=TerminalOrderResponseFactory(),
            trading_settings=TradingSettings(
                unattended_operation_enabled=True,
                stop_on_order_error=False,
            ),
            session_store=self.session_store(),
        )
        controller.start(interval_seconds=60)

        results = controller.run_auto_cycle(force=True)

        self.assertTrue(results[0]["response"]["broker_submitted"])
        self.assertEqual(controller.state, "paused")
        self.assertIsNone(controller.next_run_at)
        self.assertEqual(
            controller.last_error,
            "order_outcome_audit_failed_reconcile_required",
        )

    def test_unattended_orders_still_obey_cash_and_daily_risk_gates(self):
        now = datetime(2026, 7, 17, 15, 0, tzinfo=timezone.utc)
        order = OrderRequest("QQQ", "buy", qty=1)
        settings = TradingSettings(
            unattended_operation_enabled=True,
            min_cash_to_buy=100,
            max_daily_buy_count=1,
        )
        low_cash = validate_order_against_settings(
            order,
            AccountSnapshot(cash=64.83, equity=64.83, buying_power=64.83),
            None,
            settings,
            TradingSessionState(),
            now,
            "dry_run",
        )
        daily_limit = validate_order_against_settings(
            order,
            AccountSnapshot(cash=500, equity=500, buying_power=500),
            None,
            settings,
            TradingSessionState(buy_count=1),
            now,
            "dry_run",
        )

        self.assertEqual(low_cash["reason"], "min_cash_to_buy_not_met")
        self.assertEqual(daily_limit["reason"], "max_daily_buy_count_reached")

    def test_unattended_learning_never_promotes_live_or_submits_order(self):
        now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ"]),
                clock=lambda: now,
                trading_settings=TradingSettings(
                    unattended_operation_enabled=True,
                ),
                session_store=self.session_store(),
                operating_store=OperatingStateStore(root / "operating.json"),
            )
            controller.start()
            completed = LearningRunResult("completed", 1, 1, (), 0, root)

            with patch.object(
                controller,
                "_execute_learning",
                return_value=completed,
            ):
                results = controller.run_operating_cycle(force=True)

            self.assertEqual(results, [])
            self.assertEqual(completed.submitted_orders, 0)
            self.assertFalse((root / "promoted_strategy.json").exists())

    def test_unattended_orders_still_obey_position_and_signal_claim_gates(self):
        now = datetime(2026, 7, 17, 15, 0, tzinfo=timezone.utc)
        settings = TradingSettings(
            unattended_operation_enabled=True,
            allow_additional_buy=False,
        )
        blocked = validate_order_against_settings(
            OrderRequest("QQQ", "buy", qty=1),
            AccountSnapshot(cash=500, equity=500, buying_power=500),
            Position("QQQ", 1, 100, 100),
            settings,
            TradingSessionState(),
            now,
            "dry_run",
        )
        key = SignalKey(
            "2026-07-17", "strategy", "1", "QQQ", "buy", now.isoformat()
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingSessionStore(Path(temp_dir) / "session.json")
            first = store.claim(key)
            second = store.claim(key)

        self.assertEqual(blocked["reason"], "additional_buy_disabled")
        self.assertTrue(first.granted)
        self.assertFalse(second.granted)
        self.assertEqual(second.reason, "signal_key_submitting")


if __name__ == "__main__":
    unittest.main()
