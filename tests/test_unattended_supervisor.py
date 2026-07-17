import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nasdaq_auto_trader.app_ui_actions import DashboardActionsMixin
from nasdaq_auto_trader.automation_coordinator import AutomationCoordinator, PreflightHealth
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.operating_state import OperatingState, OperatingStateStore
from nasdaq_auto_trader.single_instance import SingleInstanceGuard
from nasdaq_auto_trader.runtime_journal import NullRuntimeJournal
from tests.app_controller_fixtures import IsolatedControllerTestCase


class CapturingFactory:
    def __init__(self) -> None:
        self.kwargs = []

    def __call__(self, config, **kwargs):
        del config
        self.kwargs.append(kwargs)
        return SimpleNamespace()


class FailingReconciliationFactory:
    def __call__(self, config, **kwargs):
        del config, kwargs

        def fail(refresh=False):
            del refresh
            raise OSError("account offline")

        return SimpleNamespace(load_portfolio=fail)


class FakeController:
    def __init__(self, enabled: bool) -> None:
        self.trading_settings = TradingSettings(
            unattended_operation_enabled=enabled,
            unattended_interval_minutes=7,
        )
        self.started_with = None
        self.unattended_starts = 0

    def start(self, interval_seconds=None) -> None:
        self.started_with = interval_seconds

    def run_operating_cycle(self, force=False):
        return [force]

    def record_unattended_start(self) -> None:
        self.unattended_starts += 1


class UnattendedSupervisorTests(IsolatedControllerTestCase):
    def test_controller_default_does_not_write_production_runtime_journal(self):
        controller = self.create_controller(
            AppConfig(mode="dry_run"), session_store=self.session_store()
        )

        self.assertIsInstance(controller.runtime_journal, NullRuntimeJournal)

    def test_gui_starts_unattended_controller_on_launch(self):
        view = DashboardActionsMixin()
        view.controller = FakeController(True)
        started = []
        logs = []
        view._start_task = lambda label, task: started.append((label, task())) or True
        view._append_log = logs.append
        view._update_controls = lambda: None

        view._start_unattended_operation()

        self.assertEqual(view.controller.started_with, 7 * 60)
        self.assertEqual(view.controller.unattended_starts, 1)
        self.assertEqual(started, [("auto", [True])])
        self.assertTrue(any("무인 자동운영" in line for line in logs))

    def test_gui_respects_disabled_unattended_mode(self):
        view = DashboardActionsMixin()
        view.controller = FakeController(False)
        view._start_task = lambda label, task: self.fail("task must not start")
        view._append_log = lambda message: None
        view._update_controls = lambda: None

        view._start_unattended_operation()

        self.assertIsNone(view.controller.started_with)

    def test_single_instance_rejects_second_holder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "app.lock"
            first = SingleInstanceGuard(path)
            second = SingleInstanceGuard(path)
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()

    def test_unattended_start_without_live_consent_has_no_live_authorization(self):
        factory = CapturingFactory()
        controller = self.create_controller(
            AppConfig(mode="dry_run"),
            engine_factory=factory,
            trading_settings=TradingSettings(
                live_trading=True,
                dry_run=False,
                unattended_operation_enabled=True,
                unattended_live_trading_enabled=False,
            ),
            session_store=self.session_store(),
        )

        controller._create_engine()

        self.assertFalse(factory.kwargs[0]["live_order_confirmation"])

    def test_live_authorization_is_created_only_for_a_trading_cycle(self):
        factory = CapturingFactory()
        controller = self.create_controller(
            AppConfig(mode="dry_run"),
            engine_factory=factory,
            trading_settings=TradingSettings(
                live_trading=True,
                dry_run=False,
                unattended_operation_enabled=True,
                unattended_live_trading_enabled=True,
            ),
            session_store=self.session_store(),
        )

        controller._create_engine()
        controller._create_engine(authorize_live_orders=True)

        self.assertFalse(factory.kwargs[0]["live_order_confirmation"])
        self.assertTrue(factory.kwargs[1]["live_order_confirmation"])

    def test_controller_reuses_one_automatic_order_guard_across_engine_cycles(self):
        factory = CapturingFactory()
        controller = self.create_controller(
            AppConfig(mode="dry_run"),
            engine_factory=factory,
            trading_settings=TradingSettings(
                auto_symbol_selection_enabled=True,
                unattended_operation_enabled=True,
            ),
            session_store=self.session_store(),
        )

        controller._create_engine()
        controller._create_engine()

        self.assertIs(
            factory.kwargs[0]["automatic_order_guard"],
            factory.kwargs[1]["automatic_order_guard"],
        )

    def test_before_open_runs_missed_learning_before_trade_cycle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = AutomationCoordinator(
                OperatingStateStore(Path(temp_dir) / "operating.json")
            )

            result = coordinator.advance(
                datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc),
                PreflightHealth(),
                reconciliation_complete=True,
                new_data_available=True,
            )

        self.assertEqual(result.state, OperatingState.OFF_HOURS_LEARNING)

    def test_recoverable_safe_halt_keeps_scheduler_running(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ"]),
                engine_factory=FailingReconciliationFactory(),
                clock=lambda: datetime(2026, 7, 17, 21, 0, tzinfo=timezone.utc),
                trading_settings=TradingSettings(
                    unattended_operation_enabled=True,
                ),
                session_store=self.session_store(),
                operating_store=OperatingStateStore(Path(temp_dir) / "operating.json"),
            )
            controller.start()

            controller.run_operating_cycle(force=True)

        self.assertEqual(controller.state, "running")
        self.assertEqual(controller.last_error, "account_state_unavailable")
        self.assertIsNotNone(controller.next_run_at)

    def test_learning_data_outage_schedules_unattended_retry(self):
        now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = self.create_controller(
                AppConfig(mode="dry_run", symbols=["QQQ"]),
                clock=lambda: now,
                trading_settings=TradingSettings(
                    unattended_operation_enabled=True,
                ),
                session_store=self.session_store(),
                operating_store=OperatingStateStore(Path(temp_dir) / "operating.json"),
            )
            controller.start(interval_seconds=15 * 60)

            with patch.object(
                controller,
                "_execute_learning",
                side_effect=OSError("market data offline"),
            ):
                result = controller.run_operating_cycle(force=True)

            runtime_state = controller.operating_store.load()

        self.assertEqual(result, [])
        self.assertEqual(controller.state, "running")
        self.assertEqual(controller.last_error, "market_data_unavailable")
        self.assertEqual(controller.next_run_at, now + timedelta(minutes=15))
        self.assertEqual(runtime_state.state, OperatingState.SAFE_HALT)

if __name__ == "__main__":
    unittest.main()
