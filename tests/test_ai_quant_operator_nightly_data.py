import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import asdict
from pathlib import Path

from tests.ai_quant_fixtures import bars, valid_spec_payload
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.operator_cli import main
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject


class AIQuantOperatorNightlyDataTests(unittest.TestCase):
    def test_nightly_uses_configured_insane_search_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "ai_quant_config.json"
            candidate_path = root / "candidate.json"
            bars_path = root / "bars.json"
            audit_path = root / "audit.jsonl"
            research_script = root / "fake_insane_search.py"
            config = AIQuantConfig(
                ai_quant_lab_enabled=True,
                self_improvement_enabled=True,
            ).to_json_object()
            config["insane_search_command"] = [sys.executable, str(research_script)]
            config_path.write_text(json.dumps(config), encoding="utf-8")
            candidate_path.write_text(json.dumps(valid_spec_payload()), encoding="utf-8")
            bars_path.write_text(json.dumps(_bars_payload()), encoding="utf-8")
            research_script.write_text(_fake_research_script(), encoding="utf-8")

            code, payload = _run_cli(
                "--ai-config",
                str(config_path),
                "--registry-path",
                str(root / "registry.json"),
                "--promoted-path",
                str(root / "promoted.json"),
                "--spec-dir",
                str(root / "specs"),
                "--audit-log",
                str(audit_path),
                "nightly",
                "--candidate-json",
                str(candidate_path),
                "--bars-json",
                str(bars_path),
            )

        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["generated_candidates"], 1)

    def test_nightly_runs_backtest_validation_with_bars_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "ai_quant_config.json"
            candidate_path = root / "candidate.json"
            bars_path = root / "bars.json"
            audit_path = root / "audit.jsonl"
            research_script = root / "fake_insane_search.py"
            config_path.write_text(
                json.dumps(
                    AIQuantConfig(
                        ai_quant_lab_enabled=True,
                        self_improvement_enabled=True,
                    ).to_json_object()
                ),
                encoding="utf-8",
            )
            candidate_path.write_text(json.dumps(valid_spec_payload()), encoding="utf-8")
            bars_path.write_text(json.dumps(_bars_payload()), encoding="utf-8")
            research_script.write_text(_fake_research_script(), encoding="utf-8")

            code, payload = _run_cli(
                "--ai-config",
                str(config_path),
                "--registry-path",
                str(root / "registry.json"),
                "--promoted-path",
                str(root / "promoted.json"),
                "--spec-dir",
                str(root / "specs"),
                "--audit-log",
                str(audit_path),
                "nightly",
                "--insane-search-command",
                sys.executable,
                str(research_script),
                "--candidate-json",
                str(candidate_path),
                "--bars-json",
                str(bars_path),
            )
            validation_events = [
                json.loads(line)
                for line in audit_path.read_text(encoding="utf-8").splitlines()
                if json.loads(line)["event_type"] == "validation_completed"
            ]

        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["generated_candidates"], 1)
        self.assertIn("turnover_too_high", payload["reasons"])
        self.assertEqual(validation_events[0]["payload"]["missing_advanced_metrics"], [])
        self.assertIn("pbo_probability", validation_events[0]["payload"]["advanced_metrics"])


def _bars_payload() -> JsonObject:
    return {
        "QQQ": [asdict(item) for item in bars("QQQ")],
        "AAPL": [asdict(item) for item in bars("AAPL")],
    }


def _fake_research_script() -> str:
    return (
        "import hashlib\n"
        "import json\n"
        "import sys\n"
        "query = sys.argv[-1]\n"
        "slug = hashlib.sha256(query.encode('utf-8')).hexdigest()[:12]\n"
        "research_id = 'research-1' if 'trend_following' in query else f'research-{slug}'\n"
        "source_id = 'source-1' if 'trend_following' in query else f'source-{slug}'\n"
        "print(json.dumps({"
        "'research_id': research_id,"
        "'summary': f'usable research for {query}',"
        "'sources': [{'source_id': source_id, 'title': 'Research',"
        "'url': 'https://example.test/research', 'published_at': '2026-01-01',"
        "'summary': 'source summary'}]"
        "}))\n"
    )


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
