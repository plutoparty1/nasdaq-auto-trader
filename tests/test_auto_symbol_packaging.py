import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from nasdaq_auto_trader.frozen_diagnostic import (
    DiagnosticUsageError,
    parse_diagnostic_request,
    run_frozen_diagnostic,
)
from nasdaq_auto_trader.gui_launcher import run
from nasdaq_auto_trader.package_audit import find_private_package_artifacts
from tests.ai_quant_fixtures import valid_spec_payload


ROOT = Path(__file__).resolve().parents[1]


class AutoSymbolPackagingTests(unittest.TestCase):
    def test_package_audit_rejects_runtime_auto_selection_tree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache = root / "auto_selection" / "latest.json"
            cache.parent.mkdir(parents=True)
            cache.write_text("{}", encoding="utf-8")

            findings = find_private_package_artifacts(root)

        self.assertEqual(findings, (cache,))
    def test_pyinstaller_spec_and_script_bundle_default_universe(self):
        spec = (ROOT / "NasdaqAutoTrader.spec").read_text(encoding="utf-8")
        script = (ROOT / "scripts" / "build_gui_exe.ps1").read_text(
            encoding="utf-8"
        )

        for source in (spec, script):
            self.assertIn("nasdaq_100_universe.json", source)
            self.assertIn("nasdaq_auto_trader", source)
            self.assertIn("quant_data", source)
            self.assertIn("defaults", source)

        self.assertIn("exclude_binaries=True", spec)
        self.assertIn("COLLECT", spec)
        self.assertIn("upx=False", spec)
        self.assertIn("console=True", spec)
        self.assertNotIn("console=False", spec)
        self.assertIn('"dist\\NasdaqAutoTrader"', script)
        self.assertIn('$FilesToCopy = @("config.kis.json", "config.example.json")', script)

    def test_empty_diagnostic_is_sanitized_and_constructs_no_order_dependencies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "diagnostic.json"
            environment = {**os.environ, "LOCALAPPDATA": str(root / "profile")}
            with patch.dict(os.environ, environment, clear=True):
                with patch(
                    "nasdaq_auto_trader.engine.TradingEngine",
                    side_effect=AssertionError("engine must not be constructed"),
                ):
                    with patch(
                        "nasdaq_auto_trader.engine_clients.build_default_client",
                        side_effect=AssertionError("client must not be constructed"),
                    ):
                        exit_code = run_frozen_diagnostic(output)

            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["diagnostic_status"], "complete")
        self.assertFalse(payload["submitted_order"])
        self.assertFalse(payload["network_client_constructed"])
        serialized = json.dumps(payload)
        for forbidden in ("api_key", "secret", "account_no", "cash", "buying_power"):
            self.assertNotIn(forbidden, serialized)

    def test_paper_fixture_produces_selected_report_without_writing_fixture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixture = root / "fixture"
            _write_paper_fixture(fixture)
            before = _tree_snapshot(fixture)
            output = root / "diagnostic.json"

            exit_code = run_frozen_diagnostic(output, fixture)
            after = _tree_snapshot(fixture)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["selection"]["status"], "selected")
        self.assertEqual(payload["selection"]["selected_symbols"], ["AAPL"])
        self.assertEqual(before, after)
        self.assertFalse(payload["submitted_order"])

    def test_live_fixture_and_wrong_surface_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixture = root / "fixture"
            _write_paper_fixture(fixture)
            (fixture / "promoted_strategy.json").write_text("{}", encoding="utf-8")
            output = root / "diagnostic.json"

            exit_code = run_frozen_diagnostic(output, fixture)
            payload = json.loads(output.read_text(encoding="utf-8"))

            with self.assertRaises(DiagnosticUsageError):
                parse_diagnostic_request(["gui", "--diagnostic-fixture-root", str(fixture)])
            with self.assertRaises(DiagnosticUsageError):
                parse_diagnostic_request(
                    [
                        "--diagnostic-output",
                        str(output),
                        "gui",
                    ]
                )
            with self.assertRaises(DiagnosticUsageError):
                run_frozen_diagnostic(fixture / "output.json", fixture)

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["reason"], "diagnostic_live_artifacts_forbidden")

    def test_launcher_diagnostic_skips_env_and_cli_surfaces(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "diagnostic.json"
            try:
                with patch(
                    "nasdaq_auto_trader.gui_launcher._app_dir",
                    return_value=root,
                ):
                    with patch(
                        "nasdaq_auto_trader.gui_launcher._load_exe_env",
                        side_effect=AssertionError("dotenv must not be loaded"),
                    ):
                        exit_code = run(["--diagnostic-output", str(output)])
            finally:
                os.chdir(original_cwd)

            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["diagnostic_status"], "complete")

    def test_launcher_rejects_fixture_without_output_without_opening_gui(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            try:
                with patch(
                    "nasdaq_auto_trader.gui_launcher._app_dir",
                    return_value=root,
                ):
                    with patch(
                        "nasdaq_auto_trader.gui_launcher._show_error"
                    ) as show_error:
                        with redirect_stderr(StringIO()):
                            exit_code = run(
                                ["--diagnostic-fixture-root", str(root)]
                            )
            finally:
                os.chdir(original_cwd)

        self.assertEqual(exit_code, 2)
        show_error.assert_not_called()

    def test_package_audit_finds_private_runtime_files_recursively(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "safe").mkdir()
            (root / "safe" / "config.example.json").write_text("{}", encoding="utf-8")
            (root / "nested").mkdir()
            secret = root / "nested" / "strategy_registry.json"
            secret.write_text("[]", encoding="utf-8")
            settings = root / "trading_config.json"
            settings.write_text("{}", encoding="utf-8")
            (root / "logs").mkdir()
            log = root / "logs" / "trader.log"
            log.write_text("private runtime log", encoding="utf-8")

            findings = find_private_package_artifacts(root)

        self.assertEqual(findings, (log, secret, settings))


def _write_paper_fixture(root: Path) -> None:
    spec = valid_spec_payload()
    spec["strategy_id"] = "diagnostic"
    spec["entry_rule"]["top_n"] = 1
    (root / "strategy_specs").mkdir(parents=True)
    (root / "strategy_specs" / "diagnostic-v1.json").write_text(
        json.dumps(spec),
        encoding="utf-8",
    )
    record = {
        "strategy_id": "diagnostic",
        "version": "v1",
        "status": "paper_candidate",
        "allowed_for_live": False,
        "manual_approval": False,
        "research_basis": spec["research_basis"],
        "score": 1.0,
        "rejection_reasons": [],
    }
    (root / "strategy_registry.json").write_text(
        json.dumps([record]),
        encoding="utf-8",
    )
    bars = []
    for index in range(80):
        close = 100 + index
        bars.append(
            {
                "symbol": "AAPL",
                "timestamp": (
                    f"2026-07-10T16:{index % 60:02d}:{index // 60:02d}+00:00"
                ),
                "open": close - 0.5,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1_000_000 + index,
            }
        )
    (root / "bars.json").write_text(
        json.dumps({"AAPL": bars}),
        encoding="utf-8",
    )


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


if __name__ == "__main__":
    unittest.main()
