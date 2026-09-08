import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests.ai_quant_fixtures import promoted_payload
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.operator_cli import main
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject


class AIQuantOperatorCliTests(unittest.TestCase):
    def test_status_reports_fail_closed_defaults_through_module_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "nasdaq_auto_trader",
                    "ai-quant",
                    "--registry-path",
                    str(Path(temp_dir) / "registry.json"),
                    "--promoted-path",
                    str(Path(temp_dir) / "promoted.json"),
                    "status",
                ],
                capture_output=True,
                check=False,
                encoding="utf-8",
                timeout=10,
            )

        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(payload["command"], "status")
        self.assertTrue(payload["config_valid"])
        self.assertEqual(payload["live_block_reason"], "live_trading_disabled")
        self.assertFalse(payload["promoted_present"])

    def test_nightly_fails_closed_when_insane_search_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "ai_quant_config.json"
            config_path.write_text(
                json.dumps(
                    AIQuantConfig(
                        ai_quant_lab_enabled=True,
                        self_improvement_enabled=True,
                    ).to_json_object()
                ),
                encoding="utf-8",
            )
            code, payload = _run_cli(
                "--ai-config",
                str(config_path),
                "--registry-path",
                str(Path(temp_dir) / "registry.json"),
                "--promoted-path",
                str(Path(temp_dir) / "promoted.json"),
                "--audit-log",
                str(Path(temp_dir) / "audit.jsonl"),
                "nightly",
            )

        self.assertEqual(code, 2)
        self.assertEqual(payload["command"], "nightly")
        self.assertEqual(payload["status"], "aborted")
        self.assertIn("insane_search_unavailable", payload["reasons"])
        self.assertEqual(payload["generated_candidates"], 0)

    def test_paper_shadow_writes_ledger_without_submitting_orders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger_path = Path(temp_dir) / "paper.jsonl"
            code, payload = _run_cli(
                "--artifact-root",
                temp_dir,
                "--audit-log",
                str(Path(temp_dir) / "audit.jsonl"),
                "paper-shadow",
                "--ledger-path",
                str(ledger_path),
                "--strategy-id",
                "strategy-1",
                "--strategy-version",
                "v1",
                "--symbol",
                "QQQ",
                "--side",
                "buy",
                "--price",
                "100",
            )

            ledger_lines = ledger_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(code, 0)
        self.assertEqual(payload["command"], "paper-shadow")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["submitted_orders"], 0)
        self.assertEqual(payload["fills"], 1)
        self.assertEqual(len(ledger_lines), 1)

    def test_live_cycle_blocks_before_existing_broker_construction_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            code, payload = _run_cli(
                "--registry-path",
                str(Path(temp_dir) / "registry.json"),
                "--promoted-path",
                str(Path(temp_dir) / "promoted.json"),
                "--audit-log",
                str(Path(temp_dir) / "audit.jsonl"),
                "live-cycle",
            )

        self.assertEqual(code, 2)
        self.assertEqual(payload["command"], "live-cycle")
        self.assertEqual(payload["status"], "blocked")
        self.assertIn("live_trading_disabled", payload["blocked_reasons"])

    def test_rollback_rewrites_promoted_strategy_to_no_trade(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            promoted_path = Path(temp_dir) / "promoted.json"
            audit_path = Path(temp_dir) / "audit.jsonl"
            promoted_path.write_text(json.dumps(promoted_payload("s1")), encoding="utf-8")

            code, payload = _run_cli(
                "--registry-path",
                str(Path(temp_dir) / "registry.json"),
                "--promoted-path",
                str(promoted_path),
                "--audit-log",
                str(audit_path),
                "rollback",
                "--reason",
                "strategy_drawdown_limit_exceeded",
            )
            promoted = json.loads(promoted_path.read_text(encoding="utf-8"))
            audit_events = [
                json.loads(line)["event_type"]
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(code, 0)
        self.assertEqual(payload["command"], "rollback")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["target_status"], "rollback")
        self.assertEqual(promoted["status"], "rollback")
        self.assertFalse(promoted["allowed_for_live"])
        self.assertEqual(promoted["mode"], "no_trade")
        self.assertIn("rollback_triggered", audit_events)

    def test_monitor_degradation_rolls_back_promoted_strategy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            promoted_path = root / "promoted.json"
            ledger_path = root / "paper.jsonl"
            config_path = root / "ai_quant_config.json"
            audit_path = root / "audit.jsonl"
            config_path.write_text(
                json.dumps(AIQuantConfig(max_strategy_drawdown_pct=0.02).to_json_object()),
                encoding="utf-8",
            )
            promoted_path.write_text(json.dumps(promoted_payload("s1")), encoding="utf-8")
            ledger_path.write_text(
                json.dumps(
                    {
                        "strategy_id": "s1",
                        "strategy_version": "v1",
                        "mode": "paper",
                        "status": "completed",
                        "fills": [],
                        "equity_curve": [100_000.0, 97_000.0],
                        "net_pnl": -3_000.0,
                        "champion_delta": 0.0,
                        "blocked_reasons": [],
                        "submitted_orders": 0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = _run_cli(
                "--ai-config",
                str(config_path),
                "--registry-path",
                str(root / "registry.json"),
                "--promoted-path",
                str(promoted_path),
                "--audit-log",
                str(audit_path),
                "monitor-degradation",
                "--ledger-path",
                str(ledger_path),
            )
            promoted = json.loads(promoted_path.read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(payload["command"], "monitor-degradation")
        self.assertEqual(payload["status"], "rolled_back")
        self.assertEqual(promoted["status"], "rollback")
        self.assertFalse(promoted["allowed_for_live"])


def _run_cli(*args: str) -> tuple[int, JsonObject]:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        code = main(list(args))
    payload = json.loads(stdout.getvalue())
    if not isinstance(payload, dict):
        raise AssertionError(payload)
    return code, payload


if __name__ == "__main__":
    unittest.main()
