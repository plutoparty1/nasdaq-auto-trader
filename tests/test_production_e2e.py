from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ProductionE2ETests(unittest.TestCase):
    def test_cli_help_and_invalid_command_contract(self):
        help_result = _run_cli("--help")
        invalid_result = _run_cli("--definitely-invalid")

        self.assertEqual(help_result.returncode, 0)
        self.assertIn("nasdaq-auto-trader", help_result.stdout)
        self.assertEqual(invalid_result.returncode, 2)
        self.assertIn("usage:", invalid_result.stderr)

    def test_source_diagnostic_constructs_no_network_or_order_client(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "diagnostic.json"

            result = _run_module(
                "nasdaq_auto_trader.gui_launcher",
                "--diagnostic-output",
                str(output),
                local_app_data=Path(temp_dir) / "appdata",
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["diagnostic_status"], "complete")
        self.assertFalse(payload["submitted_order"])
        self.assertFalse(payload["network_client_constructed"])

    def test_show_config_masks_credentials_at_process_boundary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "dry_run",
                        "broker": "alpaca",
                        "alpaca": {
                            "api_key": "private-key",
                            "secret_key": "private-secret",
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = _run_cli("--config", str(config_path), "show-config")

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("private-key", result.stdout)
        self.assertNotIn("private-secret", result.stdout)
        self.assertIn('"api_key": "***"', result.stdout)

    def test_show_config_accepts_windows_utf8_bom(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps({"mode": "dry_run", "symbols": ["QQQ"]}),
                encoding="utf-8-sig",
            )

            result = _run_cli("--config", str(config_path), "show-config")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["mode"], "dry_run")

    def test_offline_dry_run_once_never_reports_submitted_order(self):
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

            result = _run_cli("--config", str(config_path), "once")

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        responses = [item.get("response") for item in payload]
        self.assertFalse(
            any(
                isinstance(response, dict)
                and response.get("status") in {"submitted", "accepted", "filled"}
                for response in responses
            )
        )


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return _run_module("nasdaq_auto_trader", *arguments)


def _run_module(
    module: str,
    *arguments: str,
    local_app_data: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if local_app_data is not None:
        environment["LOCALAPPDATA"] = str(local_app_data)
    return subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


if __name__ == "__main__":
    unittest.main()
