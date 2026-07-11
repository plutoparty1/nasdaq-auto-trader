import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nasdaq_auto_trader.app_ui_render import DashboardRenderMixin
from nasdaq_auto_trader.config_manager import TradingSettings


class AutoSymbolGuiStorageTests(unittest.TestCase):
    def test_relative_gui_log_path_resolves_under_application_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work = root / "install"
            work.mkdir()
            view = DashboardRenderMixin()
            view.controller = SimpleNamespace(
                trading_settings=TradingSettings(
                    save_log=True,
                    log_path="logs/test-runtime.log",
                )
            )
            previous = Path.cwd()
            try:
                os.chdir(work)
                with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "appdata")}):
                    view._append_log_file("line\n")
            finally:
                os.chdir(previous)

            expected = (
                root
                / "appdata"
                / "NasdaqAutoTrader"
                / "logs"
                / "test-runtime.log"
            )
            self.assertTrue(expected.exists())


if __name__ == "__main__":
    unittest.main()
