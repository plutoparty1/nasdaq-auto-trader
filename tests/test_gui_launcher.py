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
        button_texts = {call.kwargs.get("text") for call in ttk_module.Button.call_args_list}
        label_texts = {call.kwargs.get("text") for call in ttk_module.Label.call_args_list}
        self.assertEqual(len(button_texts), 7)
        self.assertNotIn("설정", button_texts)
        self.assertFalse(any("간격" in str(text) for text in label_texts))
        ttk_module.Spinbox.assert_not_called()

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

    def test_dashboard_app_starts_with_internal_interval(self):
        app = DashboardApp.__new__(DashboardApp)
        app.controller = Mock()
        app._append_log = Mock()
        app._start_task = Mock()
        app._update_controls = Mock()

        app._start_auto_trading()

        app.controller.start.assert_called_once_with()
        app._start_task.assert_called_once()

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
                    patch(
                        "nasdaq_auto_trader.gui_launcher.SingleInstanceGuard.acquire",
                        return_value=True,
                    ),
                    patch("nasdaq_auto_trader.cli.main", side_effect=ValueError("bad config")),
                    patch.object(sys, "argv", ["launcher.exe"]),
                ):
                    exit_code = run()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(exit_code, 1)
        self.assertEqual(show_error.call_count, 1)
        self.assertIn("bad config", show_error.call_args.args[0])

    def test_duplicate_gui_launch_activates_existing_window_without_blocking_dialog(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir)
            try:
                with (
                    patch("nasdaq_auto_trader.gui_launcher._app_dir", return_value=app_dir),
                    patch("nasdaq_auto_trader.gui_launcher._load_exe_env", return_value=[]),
                    patch("nasdaq_auto_trader.gui_launcher._default_argv", return_value=["gui"]),
                    patch(
                        "nasdaq_auto_trader.gui_launcher.SingleInstanceGuard.acquire",
                        return_value=False,
                    ),
                    patch(
                        "nasdaq_auto_trader.gui_launcher._activate_existing_gui"
                    ) as activate_existing,
                    patch("nasdaq_auto_trader.gui_launcher._show_error") as show_error,
                    patch.object(sys, "argv", ["launcher.exe"]),
                ):
                    exit_code = run()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(exit_code, 0)
        activate_existing.assert_called_once_with()
        show_error.assert_not_called()

    def test_invalid_explicit_cli_arguments_exit_without_blocking_dialog(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir)
            try:
                with (
                    patch("nasdaq_auto_trader.gui_launcher._app_dir", return_value=app_dir),
                    patch("nasdaq_auto_trader.gui_launcher._load_exe_env", return_value=[]),
                    patch("nasdaq_auto_trader.gui_launcher._show_error") as show_error,
                    patch("nasdaq_auto_trader.cli.main", side_effect=SystemExit(2)),
                ):
                    exit_code = run(["--definitely-invalid"])
            finally:
                os.chdir(original_cwd)

        self.assertEqual(exit_code, 2)
        show_error.assert_not_called()

    def test_explicit_cli_runtime_error_prints_without_blocking_dialog(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            app_dir = Path(tmpdir)
            try:
                with (
                    patch("nasdaq_auto_trader.gui_launcher._app_dir", return_value=app_dir),
                    patch("nasdaq_auto_trader.gui_launcher._load_exe_env", return_value=[]),
                    patch("nasdaq_auto_trader.gui_launcher._show_error") as show_error,
                    patch("nasdaq_auto_trader.cli.main", side_effect=PermissionError("denied")),
                    patch("sys.stderr", new_callable=StringIO) as stderr,
                ):
                    exit_code = run(["live-canary"])
            finally:
                os.chdir(original_cwd)

        self.assertEqual(exit_code, 1)
        self.assertIn("denied", stderr.getvalue())
        show_error.assert_not_called()

    def test_exe_launcher_loads_env_next_to_dist_or_parent_without_overriding(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dist = root / "dist"
            dist.mkdir()
            (root / ".env").write_text(
                "KIS_APP_KEY=from-parent\nKIS_ACCOUNT_NO=12345678\nIGNORED_KEY=x\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "KIS_APP_KEY": "already-set",
                    "LOCALAPPDATA": str(root / "private-appdata"),
                },
                clear=True,
            ):
                loaded = _load_exe_env(dist)
                self.assertEqual(os.environ["KIS_APP_KEY"], "already-set")
                self.assertEqual(os.environ["KIS_ACCOUNT_NO"], "12345678")
                self.assertEqual(loaded, [root / ".env"])
                self.assertNotIn("IGNORED_KEY", os.environ)

    def test_exe_launcher_prefers_private_app_data_env(self):
        original_account = os.environ.get("KIS_ACCOUNT_NO")
        try:
            os.environ.pop("KIS_ACCOUNT_NO", None)
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                app_data = root / "AppData" / "Local"
                private_dir = app_data / "NasdaqAutoTrader"
                private_dir.mkdir(parents=True)
                private_env = private_dir / ".env"
                private_env.write_text(
                    "KIS_ACCOUNT_NO=87654321\n",
                    encoding="utf-8",
                )
                app_dir = root / "dist" / "NasdaqAutoTrader"
                app_dir.mkdir(parents=True)

                with patch.dict(
                    os.environ,
                    {"LOCALAPPDATA": str(app_data)},
                    clear=False,
                ):
                    loaded = _load_exe_env(app_dir)
                    self.assertEqual(loaded, [private_env])
                    self.assertEqual(os.environ["KIS_ACCOUNT_NO"], "87654321")
        finally:
            if original_account is None:
                os.environ.pop("KIS_ACCOUNT_NO", None)
            else:
                os.environ["KIS_ACCOUNT_NO"] = original_account


if __name__ == "__main__":
    unittest.main()
