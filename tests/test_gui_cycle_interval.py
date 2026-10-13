from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nasdaq_auto_trader.app_controller import AutoTradeController
from nasdaq_auto_trader.app_ui import DashboardApp
from nasdaq_auto_trader.automation_coordinator import AutomationCoordinator
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.operating_state import (
    OperatingState,
    OperatingStateStore,
    RuntimeState,
)
from nasdaq_auto_trader.trading_session_store import TradingSessionStore


@pytest.mark.parametrize("interval_minutes", [5, 15])
def test_manual_start_schedules_next_cycle_at_configured_interval(
    tmp_path: Path, interval_minutes: int,
) -> None:
    # Given a paused GUI with the default one-hour controller interval.
    now = datetime(2026, 9, 22, 13, 20, tzinfo=timezone.utc)
    engine_factory = Mock(side_effect=AssertionError("No broker work before opening"))
    controller = AutoTradeController(
        AppConfig(mode="dry_run"),
        engine_factory=engine_factory,
        clock=lambda: now,
        trading_settings=TradingSettings(
            unattended_operation_enabled=True,
            unattended_interval_minutes=interval_minutes,
        ),
        session_store=TradingSessionStore(tmp_path / "session.json"),
    )
    store = OperatingStateStore(tmp_path / "operating.json")
    store.save(RuntimeState(
        OperatingState.PRE_MARKET_CHECK, now,
        last_learning_market_date="2026-09-21",
    ))
    controller.operating_store = store
    controller.operating_coordinator = AutomationCoordinator(store)
    app = DashboardApp.__new__(DashboardApp)
    app.controller = controller
    app.messagebox = Mock()

    # When the user starts automatic operation and its first cycle finishes.
    with patch.multiple(
        DashboardApp, _append_log=Mock(), _start_task=Mock(), _update_controls=Mock(),
    ):
        app._start_auto_trading()
        app._start_task.call_args.args[1]()

    # Then the next cycle is due exactly at the configured minute boundary.
    assert controller.next_run_at == now + timedelta(minutes=interval_minutes)
    now += timedelta(minutes=interval_minutes, seconds=-1)
    assert controller.is_due() is False
    now += timedelta(seconds=1)
    assert controller.is_due() is True
    engine_factory.assert_not_called()
