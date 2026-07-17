import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.engine_errors import PreOrderCycleError
from nasdaq_auto_trader.operating_state import StateTransitionError
from tests.app_controller_fixtures import IsolatedControllerTestCase


class OperatingCycleRecoveryTests(IsolatedControllerTestCase):
    def _running_controller(self, now: datetime) -> AutoTradeController:
        controller = self.create_controller(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            clock=lambda: now,
            trading_settings=TradingSettings(unattended_operation_enabled=True),
            session_store=self.session_store(),
            operating_store=self.operating_store(),
        )
        controller.start(interval_seconds=60)
        return controller

    def test_recoverable_preflight_error_schedules_a_bounded_retry(self) -> None:
        now = datetime(2026, 7, 17, 14, 0, tzinfo=timezone.utc)
        controller = self._running_controller(now)

        # Given: unattended operation is due and preflight reports a recoverable error.
        with patch.object(
            controller,
            "_operating_health",
            side_effect=PreOrderCycleError("market_data_unavailable"),
        ):
            # When: the operating cycle evaluates preflight before running orders.
            result = controller.run_operating_cycle(force=True)

        # Then: it keeps running but is not immediately due again.
        self.assertEqual(result, [])
        self.assertEqual(controller.state, "running")
        self.assertEqual(controller.last_error, "market_data_unavailable")
        self.assertEqual(controller.next_run_at, now + timedelta(seconds=60))
        self.assertFalse(controller.is_due())

    def test_operating_store_error_pauses_the_unattended_scheduler(self) -> None:
        now = datetime(2026, 7, 17, 14, 0, tzinfo=timezone.utc)
        controller = self._running_controller(now)

        # Given: the operating-state store cannot provide a trustworthy pre-cycle state.
        with patch.object(
            controller.operating_store,
            "load",
            side_effect=StateTransitionError("runtime_state_corrupt"),
        ):
            # When: the operating cycle starts its state evaluation.
            result = controller.run_operating_cycle(force=True)

        # Then: it fails closed so auto-cycle priority cannot starve report work.
        self.assertEqual(result, [])
        self.assertEqual(controller.state, "paused")
        self.assertEqual(controller.last_error, "runtime_state_corrupt")
        self.assertIsNone(controller.next_run_at)
        self.assertFalse(controller.is_due())


if __name__ == "__main__":
    unittest.main()
