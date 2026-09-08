import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from nasdaq_auto_trader.__main__ import main as module_main
from nasdaq_auto_trader.cli import main


class CliDryRunSurfaceTests(unittest.TestCase):
    def test_missing_backtest_csv_returns_controlled_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.csv"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch.object(
                    sys,
                    "argv",
                    ["nasdaq_auto_trader", "backtest", "--csv", str(missing)],
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = module_main()

        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("CSV file", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_module_entrypoint_reports_malformed_config_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "invalid.json"
            config_path.write_text("{ invalid json", encoding="utf-8")
            stderr = io.StringIO()

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "nasdaq_auto_trader",
                        "--config",
                        str(config_path),
                        "once",
                        "--mode",
                        "dry_run",
                    ],
                ),
                redirect_stderr(stderr),
            ):
                code = module_main()

        self.assertEqual(code, 2)
        self.assertIn("invalid configuration", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_once_dry_run_does_not_require_broker_credentials(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "dry_run",
                        "broker": "alpaca",
                        "symbols": ["QQQ"],
                        "alpaca": {"api_key": "", "secret_key": ""},
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["--config", str(config_path), "once", "--mode", "dry_run"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload[0]["symbol"], "QQQ")
        self.assertIsNone(payload[0]["response"])


if __name__ == "__main__":
    unittest.main()
