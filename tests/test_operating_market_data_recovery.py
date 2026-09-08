from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from nasdaq_auto_trader.app_controller import AutoTradeController
from nasdaq_auto_trader.automation_coordinator import AutomationCoordinator, PreflightHealth
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.learning_runner import LearningRunResult
from nasdaq_auto_trader.operating_state import OperatingState, OperatingStateStore
from nasdaq_auto_trader.trading_session_store import TradingSessionStore


def controller_at(root: Path, now: datetime) -> AutoTradeController:
    controller = AutoTradeController(
        AppConfig(),
        clock=lambda: now,
        trading_settings=TradingSettings(unattended_operation_enabled=True),
        session_store=TradingSessionStore(root / "session.json"),
    )
    controller.operating_store = OperatingStateStore(root / "operating.json")
    controller.operating_coordinator = AutomationCoordinator(controller.operating_store)
    controller.start(interval_seconds=60)
    return controller


@pytest.mark.parametrize("status", ["completed", "blocked"])
def test_learning_clears_connection_error_after_market_data_recovers(
    tmp_path: Path, status: str,
) -> None:
    # Given: the last learning data request failed before reaching the learner.
    now = datetime(2026, 9, 8, 0, 4, 48, tzinfo=timezone.utc)
    controller = controller_at(tmp_path, now)
    with patch.object(controller, "_execute_learning", side_effect=OSError("offline")):
        controller.run_operating_cycle(force=True)
    assert controller.last_error == "market_data_unavailable"

    # When: retrying reaches the learner (which can reject unsuitable data).
    result = LearningRunResult(status, 0, 0, (), 0, tmp_path)
    with patch.object(controller, "_execute_learning", return_value=result):
        controller.run_operating_cycle(force=True)

    # Then: the recovered transport no longer leaves a retry warning active.
    assert controller.last_error is None
    assert controller.state == "running"
    assert controller.operating_store.load().state is OperatingState.OFF_HOURS_LEARNING
    assert controller.next_run_at == now + timedelta(seconds=60)


def test_learning_keeps_retry_warning_while_market_data_is_offline(tmp_path: Path) -> None:
    # Given: an unattended learning cycle with an unavailable market data source.
    now = datetime(2026, 9, 8, 0, 4, 48, tzinfo=timezone.utc)
    controller = controller_at(tmp_path, now)
    controller.last_error = "market_data_unavailable"

    # When: the next data request also fails.
    with patch.object(controller, "_execute_learning", side_effect=OSError("offline")):
        controller.run_operating_cycle(force=True)

    # Then: the failure remains visible and the scheduler retains a bounded retry.
    assert controller.last_error == "market_data_unavailable"
    assert controller.operating_store.load().state is OperatingState.SAFE_HALT
    assert controller.next_run_at == now + timedelta(seconds=60)


def test_learning_does_not_clear_unrelated_account_error(tmp_path: Path) -> None:
    # Given: learning has not checked the account that previously failed.
    controller = controller_at(tmp_path, datetime(2026, 9, 8, tzinfo=timezone.utc))
    controller.last_error = "account_state_unavailable"
    result = LearningRunResult("completed", 0, 0, (), 0, tmp_path)

    # When: only the market data and learning operation succeed.
    with patch.object(controller, "_execute_learning", return_value=result):
        controller.run_operating_cycle(force=True)

    # Then: account health is not falsely declared recovered.
    assert controller.last_error == "account_state_unavailable"


def test_successful_shadow_scan_clears_previous_connection_error(tmp_path: Path) -> None:
    # Given: an intraday scan can recover market data without a trading strategy.
    controller = controller_at(
        tmp_path, datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc),
    )
    controller.last_error = "market_data_unavailable"

    # When: a scan completes successfully through the ordinary operating cycle.
    with (
        patch.object(controller, "_operating_health", return_value=PreflightHealth(model_ok=False)),
        patch("nasdaq_auto_trader.controller_operations.run_intraday_shadow_scan"),
    ):
        controller.run_operating_cycle(force=True)

    # Then: the scan, not an order or unrelated account refresh, clears the warning.
    assert controller.last_error is None
    assert controller.operating_store.load().state is OperatingState.INTRADAY_SHADOW_SCAN
