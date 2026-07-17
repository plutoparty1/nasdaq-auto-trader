import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from nasdaq_auto_trader.app_ui_render import DashboardRenderMixin
from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import SettingsError, TradingSettings
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.app_controller_fixtures import IsolatedControllerTestCase


class GuiLiveModeTests(IsolatedControllerTestCase):
    def test_gui_live_action_reaches_confirmed_engine_factory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            factory = _RecordingFactory()
            controller = self.create_controller(
                AppConfig(
                    live_environment_authorized=True,
                    alpaca=AlpacaCredentials("app", "secret", paper=False),
                ),
                engine_factory=factory,
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                    dry_run=False,
                    live_trading=True,
                ),
                session_store=TradingSessionStore(Path(temp_dir) / "session.json"),
            )

            controller.start()
            result = controller.run_auto_cycle(force=True)

        self.assertEqual(result, [])
        self.assertEqual(factory.calls, 1)
        self.assertEqual(factory.configs[0].mode, "live")
        self.assertIs(factory.kwargs[0]["live_order_confirmation"], True)

    def test_gui_dry_run_does_not_confirm_live_orders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            factory = _RecordingFactory()
            controller = self.create_controller(
                AppConfig(),
                engine_factory=factory,
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                    dry_run=True,
                    live_trading=True,
                ),
                session_store=TradingSessionStore(Path(temp_dir) / "session.json"),
            )

            controller.start()
            result = controller.run_auto_cycle(force=True)

        self.assertEqual(result, [])
        self.assertEqual(factory.configs[0].mode, "dry_run")
        self.assertIs(factory.kwargs[0]["live_order_confirmation"], False)

    def test_gui_live_real_engine_requires_environment_authorization(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = self.create_controller(
                AppConfig(),
                trading_settings=TradingSettings(
                    dry_run=False,
                    live_trading=True,
                ),
                session_store=TradingSessionStore(Path(temp_dir) / "session.json"),
            )
            with self.assertRaisesRegex(SettingsError, "environment authorization"):
                controller.start()

        self.assertEqual(controller.state, "stopped")

    def test_live_banner_reports_guarded_live_mode(self):
        view = DashboardRenderMixin()
        view.controller = SimpleNamespace(
            config=AppConfig(mode="live"),
            trading_settings=TradingSettings(dry_run=False, live_trading=True),
            settings_path=Path("trading.json"),
            last_selection_report=None,
        )
        view.config_path = "config.json"
        view.warning_var = _Variable("")
        view.selection_var = _Variable("")
        view.mode_var = _Variable("")
        view._append_log = lambda message: None

        view._render_mode()

        self.assertIn("실거래 활성화", view.warning_var.get())
        self.assertNotIn("모든 실행이 차단", view.warning_var.get())


class _Variable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Engine:
    last_selection_report = None

    def run_once(self):
        return []


class _RecordingFactory:
    def __init__(self):
        self.calls = 0
        self.configs = []
        self.kwargs = []

    def __call__(self, config, **kwargs):
        self.calls += 1
        self.configs.append(config)
        self.kwargs.append(kwargs)
        return _Engine()


if __name__ == "__main__":
    unittest.main()
