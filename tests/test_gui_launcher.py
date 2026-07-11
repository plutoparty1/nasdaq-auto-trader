import queue
import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from nasdaq_auto_trader.app_ui import DashboardApp, launch_gui
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import SettingsError, TradingSettings
from nasdaq_auto_trader.gui_launcher import _default_argv, _load_exe_env, _show_error, run


class GuiLauncherTests(unittest.TestCase):
    def test_dashboard_app_initializes_worker_state_before_starting_tasks(self):
        root = Mock()
        controller = Mock(
            settings_error=None,
            settings_path=Path("trading_config.json"),
            interval_seconds=3600,
        )
        tk_module = Mock()
        ttk_module = Mock()

        with patch.multiple(
            DashboardApp,
            _append_log=Mock(),
            _render_mode=Mock(),
            _start_task=Mock(),
            _poll_results=Mock(),
            _tick=Mock(),
        ):
            app = DashboardApp(
                root,
                controller,
                tk_module=tk_module,
                ttk_module=ttk_module,
                messagebox_module=Mock(),
                config_path="config.kis.json",
                portfolio_refresh_seconds=15,
            )

        self.assertIsInstance(app._result_queue, queue.Queue)
        self.assertIsNone(app._worker)
        self.assertEqual(ttk_module.Button.call_count, 6)

    def test_exe_launcher_uses_app_data_settings_path_outside_dist(self):
        original_local_app_data = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                app_dir = Path(temp_dir) / "dist" / "NasdaqAutoTrader"
                app_dir.mkdir(parents=True)
                app_data = Path(temp_dir) / "AppData" / "Local"
                os.environ["LOCALAPPDATA"] = str(app_data)

                argv = _default_argv(app_dir)

            trading_config = argv[argv.index("--trading-config") + 1]
            self.assertEqual(
                Path(trading_config),
                app_data / "NasdaqAutoTrader" / "trading_config.json",
            )
            self.assertNotIn(str(app_dir), trading_config)
        finally:
            if original_local_app_data is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = original_local_app_data

    def test_dashboard_app_reports_invalid_interval_without_starting(self):
        app = DashboardApp.__new__(DashboardApp)
        app.interval_var = Mock()
        app.interval_var.get.return_value = "0"
        app.controller = Mock()
        app.messagebox = Mock()
        app._append_log = Mock()

        app._start_auto_trading()

        app.messagebox.showerror.assert_called_once()
        app.controller.start.assert_not_called()

    def test_launch_gui_uses_safe_defaults_when_settings_loading_fails(self):
        root = Mock()

        with (
            patch(
                "nasdaq_auto_trader.app_ui.load_or_create_settings",
                side_effect=SettingsError("broken settings"),
            ),
            patch("tkinter.Tk", return_value=root),
            patch("nasdaq_auto_trader.app_ui.DashboardApp") as dashboard_app,
        ):
            launch_gui(AppConfig(), settings_path="broken.json")

        controller = dashboard_app.call_args.args[1]
        self.assertIsInstance(controller.trading_settings, TradingSettings)
        self.assertEqual(controller.settings_error, "broken settings")
        root.mainloop.assert_called_once_with()

    def test_show_error_falls_back_to_stderr_when_tk_is_unavailable(self):
        original_import = __import__

        def block_tkinter(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "tkinter" or name.startswith("tkinter."):
                raise ImportError("tk unavailable")
            return original_import(name, globals, locals, fromlist, level)

        with (
            patch("builtins.__import__", side_effect=block_tkinter),
            patch("sys.stderr", new_callable=StringIO) as stderr,
        ):
            _show_error("launcher failed")

        self.assertIn("launcher failed", stderr.getvalue())

    def test_run_reports_expected_cli_startup_errors(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir)
            try:
                with (
                    patch("nasdaq_auto_trader.gui_launcher._app_dir", return_value=app_dir),
                    patch("nasdaq_auto_trader.gui_launcher._load_exe_env", return_value=[]),
                    patch("nasdaq_auto_trader.gui_launcher._default_argv", return_value=["gui"]),
                    patch("nasdaq_auto_trader.gui_launcher._show_error") as show_error,
                    patch("nasdaq_auto_trader.cli.main", side_effect=ValueError("bad config")),
                    patch.object(sys, "argv", ["launcher.exe"]),
                ):
                    exit_code = run()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(exit_code, 1)
        self.assertEqual(show_error.call_count, 1)
        self.assertIn("bad config", show_error.call_args.args[0])

    def test_exe_launcher_loads_env_next_to_dist_or_parent_without_overriding(self):
        original_app_key = os.environ.get("KIS_APP_KEY")
        original_account = os.environ.get("KIS_ACCOUNT_NO")
        try:
            os.environ["KIS_APP_KEY"] = "already-set"
            os.environ.pop("KIS_ACCOUNT_NO", None)

            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                dist = root / "dist"
                dist.mkdir()
                (root / ".env").write_text(
                    "KIS_APP_KEY=from-parent\nKIS_ACCOUNT_NO=12345678\nIGNORED_KEY=x\n",
                    encoding="utf-8",
                )

                loaded = _load_exe_env(dist)

            self.assertEqual(os.environ["KIS_APP_KEY"], "already-set")
            self.assertEqual(os.environ["KIS_ACCOUNT_NO"], "12345678")
            self.assertEqual(len(loaded), 1)
            self.assertNotIn("IGNORED_KEY", os.environ)
        finally:
            if original_app_key is None:
                os.environ.pop("KIS_APP_KEY", None)
            else:
                os.environ["KIS_APP_KEY"] = original_app_key
            if original_account is None:
                os.environ.pop("KIS_ACCOUNT_NO", None)
            else:
                os.environ["KIS_ACCOUNT_NO"] = original_account


if __name__ == "__main__":
    unittest.main()
