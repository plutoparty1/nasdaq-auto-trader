import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.automation_coordinator import AutomationCoordinator, PreflightHealth
from nasdaq_auto_trader.operating_state import OperatingState, OperatingStateStore


class AutomationCoordinatorTests(unittest.TestCase):
    def test_open_market_missing_model_enters_read_only_shadow_scan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = AutomationCoordinator(OperatingStateStore(Path(temp_dir) / "state.json"))
            now = datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc)

            blocked = coordinator.advance(now, PreflightHealth(model_ok=False))
            ready = coordinator.advance(now, PreflightHealth())

        self.assertEqual(blocked.state, OperatingState.INTRADAY_SHADOW_SCAN)
        self.assertEqual(blocked.reason, "operating_model_unavailable")
        self.assertEqual(ready.state, OperatingState.LIVE_TRADING)

    def test_open_market_non_model_failure_still_safe_halts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = AutomationCoordinator(
                OperatingStateStore(Path(temp_dir) / "state.json")
            )

            result = coordinator.advance(
                datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
                PreflightHealth(account_ok=False),
            )

        self.assertEqual(result.state, OperatingState.SAFE_HALT)
        self.assertEqual(result.reason, "account_state_unavailable")

    def test_missing_model_does_not_hide_a_second_preflight_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = AutomationCoordinator(
                OperatingStateStore(Path(temp_dir) / "state.json")
            )

            result = coordinator.advance(
                datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
                PreflightHealth(model_ok=False, risk_config_ok=False),
            )

        self.assertEqual(result.state, OperatingState.SAFE_HALT)
        self.assertEqual(result.reason, "risk_config_invalid")

    def test_before_open_enters_pre_market_check(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = AutomationCoordinator(OperatingStateStore(Path(temp_dir) / "state.json"))

            result = coordinator.advance(
                datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc),
                PreflightHealth(),
            )

        self.assertEqual(result.state, OperatingState.PRE_MARKET_CHECK)

    def test_before_open_missing_model_stays_ready_for_opening_scan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = AutomationCoordinator(
                OperatingStateStore(Path(temp_dir) / "state.json")
            )

            result = coordinator.advance(
                datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc),
                PreflightHealth(model_ok=False),
            )

        self.assertEqual(result.state, OperatingState.PRE_MARKET_CHECK)

    def test_after_close_reconciles_before_learning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = AutomationCoordinator(OperatingStateStore(Path(temp_dir) / "state.json"))
            now = datetime(2026, 6, 26, 21, 0, tzinfo=timezone.utc)

            first = coordinator.advance(now, PreflightHealth(), reconciliation_complete=False)
            second = coordinator.advance(now, PreflightHealth(), reconciliation_complete=True, new_data_available=True)

        self.assertEqual(first.state, OperatingState.POST_MARKET_RECONCILIATION)
        self.assertEqual(second.state, OperatingState.OFF_HOURS_LEARNING)

    def test_missing_model_after_close_can_enter_recovery_learning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = AutomationCoordinator(
                OperatingStateStore(Path(temp_dir) / "state.json")
            )

            result = coordinator.advance(
                datetime(2026, 6, 26, 21, 0, tzinfo=timezone.utc),
                PreflightHealth(model_ok=False),
                reconciliation_complete=True,
                new_data_available=True,
            )

        self.assertEqual(result.state, OperatingState.OFF_HOURS_LEARNING)

    def test_emergency_stop_has_priority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = AutomationCoordinator(OperatingStateStore(Path(temp_dir) / "state.json"))

            result = coordinator.advance(
                datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
                PreflightHealth(),
                emergency_stop=True,
            )

        self.assertEqual(result.state, OperatingState.EMERGENCY_STOP)
