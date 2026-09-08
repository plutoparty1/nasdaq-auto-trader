import unittest
from unittest.mock import Mock, patch

from nasdaq_auto_trader.app_ui import launch_gui
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings


class AIAutopilotGuiTests(unittest.TestCase):
    def test_launch_gui_forces_ai_autopilot_profile(self):
        root = Mock()
        stored_settings = TradingSettings(
            live_trading=True,
            dry_run=False,
            require_confirm_before_buy=True,
            require_confirm_before_sell=True,
            auto_symbol_selection_enabled=False,
            unattended_operation_enabled=False,
            unattended_live_trading_enabled=True,
            max_position_qty=4,
            max_daily_buy_count=2,
            max_daily_sell_count=3,
            max_daily_loss_rate=2.5,
        )

        with (
            patch(
                "nasdaq_auto_trader.app_ui.load_or_create_settings",
                return_value=stored_settings,
            ),
            patch("tkinter.Tk", return_value=root),
            patch("nasdaq_auto_trader.app_ui.DashboardApp") as dashboard_app,
        ):
            launch_gui(AppConfig(), settings_path="trading_config.json")

        runtime_settings = dashboard_app.call_args.args[1].trading_settings
        self.assertTrue(runtime_settings.auto_symbol_selection_enabled)
        self.assertTrue(runtime_settings.unattended_operation_enabled)
        self.assertFalse(runtime_settings.require_confirm_before_buy)
        self.assertFalse(runtime_settings.require_confirm_before_sell)
        self.assertTrue(runtime_settings.live_trading)
        self.assertFalse(runtime_settings.dry_run)
        self.assertTrue(runtime_settings.unattended_live_trading_enabled)
        self.assertEqual(runtime_settings.max_position_qty, 4)
        self.assertEqual(runtime_settings.max_daily_buy_count, 2)
        self.assertEqual(runtime_settings.max_daily_sell_count, 3)
        self.assertEqual(runtime_settings.max_daily_loss_rate, 2.5)


if __name__ == "__main__":
    unittest.main()
