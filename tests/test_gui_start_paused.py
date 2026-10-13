from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nasdaq_auto_trader.app_controller import AutoTradeController
from nasdaq_auto_trader.app_types import PortfolioSnapshot, PositionRow
from nasdaq_auto_trader.app_ui import DashboardApp, launch_gui
from nasdaq_auto_trader.app_ui_actions import DashboardActionsMixin
from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.cli_main import main
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.trading_session_store import TradingSessionStore


@pytest.mark.parametrize("start_paused", [True, False])
def test_gui_cli_propagates_session_start_option(start_paused: bool) -> None:
    argv = ["gui", "--start-paused"] if start_paused else ["gui"]
    with (
        patch("nasdaq_auto_trader.cli_main.load_config", return_value=AppConfig()),
        patch("nasdaq_auto_trader.app.launch_gui") as launch,
    ):
        assert main(argv) == 0

    assert launch.call_args.kwargs["start_paused"] is start_paused


def test_launch_gui_preserves_live_settings_when_starting_paused() -> None:
    settings = TradingSettings(live_trading=True, dry_run=False)
    with (
        patch("nasdaq_auto_trader.app_ui.load_or_create_settings", return_value=settings),
        patch("nasdaq_auto_trader.app_ui.AutoTradeController") as controller,
        patch("nasdaq_auto_trader.app_ui.DashboardApp") as dashboard,
        patch("tkinter.Tk"),
    ):
        launch_gui(AppConfig(), start_paused=True)

    applied = controller.call_args.kwargs["trading_settings"]
    assert applied.live_trading is True
    assert applied.dry_run is False
    assert applied.unattended_operation_enabled is True
    assert dashboard.call_args.kwargs["start_paused"] is True


@pytest.mark.parametrize("start_paused", [True, False])
def test_dashboard_startup_waits_for_user_only_when_requested(
    tmp_path: Path, start_paused: bool,
) -> None:
    engine = Mock()
    engine.load_portfolio.return_value = (
        AccountSnapshot(cash=50, equity=50, buying_power=50), {},
    )
    factory = Mock(return_value=engine)
    controller = AutoTradeController(
        AppConfig(
            live_environment_authorized=True,
            alpaca=AlpacaCredentials("test-app", "test-secret", paper=False),
        ),
        engine_factory=factory,
        trading_settings=TradingSettings(
            live_trading=True,
            dry_run=False,
            unattended_operation_enabled=True,
            unattended_live_trading_enabled=True,
        ),
        session_store=TradingSessionStore(tmp_path / "session.json"),
    )
    with (
        patch.multiple(
            DashboardApp,
            _build_ui=Mock(),
            _append_log=Mock(),
            _render_mode=Mock(),
            _update_controls=Mock(),
            _start_task=Mock(return_value=True),
            _poll_results=Mock(),
            _tick=Mock(),
        ),
        patch("nasdaq_auto_trader.app_ui.apply_operator_theme"),
    ):
        app = DashboardApp(
            Mock(), controller, Mock(), Mock(), Mock(), None, 15,
            start_paused=start_paused,
        )
        expected_label = "portfolio" if start_paused else "auto"
        assert app._start_task.call_args.args[0] == expected_label
        assert controller.state == ("stopped" if start_paused else "running")
        assert controller.is_due() is not start_paused

        if start_paused:
            refresh = app._start_task.call_args.args[1]
            assert refresh().account.cash == 50
            assert factory.call_args.kwargs["live_order_confirmation"] is False
            engine.run_once.assert_not_called()
            app._start_task.reset_mock()
            app._next_portfolio_refresh = float("inf")
            with patch.object(app._daily_report_service, "is_due", return_value=False):
                DashboardActionsMixin._tick(app)
            app._start_task.assert_not_called()
            assert controller.run_operating_cycle(force=True) is None
            assert controller.state == "stopped"

            snapshot = PortfolioSnapshot(
                datetime.now(timezone.utc), "live", "alpaca",
                AccountSnapshot(cash=50, equity=61, buying_power=50),
                [PositionRow("TEST", 1, 10, 11, 11, 1, 10)],
            )
            app._result_queue.put(("ok", "portfolio", snapshot))
            with patch.object(app, "_render_snapshot"):
                DashboardActionsMixin._poll_results(app)
            app._start_task.assert_not_called()
            assert controller.state == "stopped"

            app._start_auto_trading()
            assert controller.state == "running"
            assert app._start_task.call_args.args[0] == "auto"
