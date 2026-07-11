import json
import tempfile
import unittest
from pathlib import Path

from tests.ai_quant_fixtures import promoted_payload
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.degradation_monitor import DegradationMonitor
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject


class AIQuantDegradationMonitorTests(unittest.TestCase):
    def test_monitor_rolls_back_when_ledger_breaches_drawdown_limit(self):
        audit = NullAuditLogger()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ledger_path = root / "paper.jsonl"
            promoted_path = root / "promoted.json"
            registry = StrategyRegistry(
                root / "registry.json",
                promoted_path,
                AIQuantConfig(max_strategy_drawdown_pct=0.02),
                audit,
            )
            promoted_path.write_text(json.dumps(promoted_payload("s1")), encoding="utf-8")
            ledger_path.write_text(
                json.dumps(_ledger_entry("s1", "v1", (100_000.0, 99_000.0))) + "\n"
                + json.dumps(_ledger_entry("s1", "v1", (99_000.0, 97_000.0))) + "\n",
                encoding="utf-8",
            )

            result = DegradationMonitor(registry.config, registry, audit).evaluate(ledger_path)
            promoted = registry.load_promoted_strategy()

        self.assertEqual(result.status, "rolled_back")
        self.assertIn("strategy_drawdown_limit_exceeded", result.reasons)
        self.assertEqual(promoted["status"], "rollback")
        self.assertEqual(promoted["mode"], "no_trade")
        self.assertIn("strategy_degradation_detected", [event.event_type for event in audit.events])
        self.assertIn("rollback_triggered", [event.event_type for event in audit.events])

    def test_monitor_rolls_back_when_ledger_is_missing(self):
        audit = NullAuditLogger()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            promoted_path = root / "promoted.json"
            registry = StrategyRegistry(
                root / "registry.json",
                promoted_path,
                AIQuantConfig(),
                audit,
            )
            promoted_path.write_text(json.dumps(promoted_payload("s1")), encoding="utf-8")

            result = DegradationMonitor(registry.config, registry, audit).evaluate(
                root / "missing-paper.jsonl"
            )
            promoted = registry.load_promoted_strategy()

        self.assertEqual(result.status, "rolled_back")
        self.assertIn("performance_ledger_missing", result.reasons)
        self.assertEqual(promoted["status"], "rollback")

    def test_monitor_rolls_back_when_ledger_contains_oversized_integer(self):
        audit = NullAuditLogger()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ledger_path = root / "paper.jsonl"
            promoted_path = root / "promoted.json"
            registry = StrategyRegistry(
                root / "registry.json",
                promoted_path,
                AIQuantConfig(),
                audit,
            )
            promoted_path.write_text(json.dumps(promoted_payload("s1")), encoding="utf-8")
            ledger_path.write_text(
                (
                    '{"strategy_id":"s1","strategy_version":"v1","status":"completed",'
                    '"equity_curve":[100000,'
                    f'{"9" * 10_000}'
                    "]}\n"
                ),
                encoding="utf-8",
            )

            result = DegradationMonitor(registry.config, registry, audit).evaluate(ledger_path)
            promoted = registry.load_promoted_strategy()

        self.assertEqual(result.status, "rolled_back")
        self.assertIn("performance_ledger_malformed", result.reasons)
        self.assertEqual(promoted["status"], "rollback")


def _ledger_entry(
    strategy_id: str,
    strategy_version: str,
    equity_curve: tuple[float, ...],
) -> JsonObject:
    return {
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "mode": "paper",
        "status": "completed",
        "fills": [],
        "equity_curve": list(equity_curve),
        "net_pnl": equity_curve[-1] - equity_curve[0],
        "champion_delta": 0.0,
        "blocked_reasons": [],
        "submitted_orders": 0,
    }


if __name__ == "__main__":
    unittest.main()
