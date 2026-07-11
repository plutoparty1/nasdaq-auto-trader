import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.config import load_ai_quant_config
from nasdaq_auto_trader.ai_quant_lab.operator_models import OperatorPaths
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.registry_models import StrategyStatus
from nasdaq_auto_trader.learning_runner import LearningCancellation, run_learning_only
from nasdaq_auto_trader.quant_data.features import PriceBar
from nasdaq_auto_trader.quant_data.symbol_selector import ResolvedStrategy, resolve_strategy
from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths


class LearningRunnerTests(unittest.TestCase):
    def test_learning_only_creates_safe_local_config_and_submits_no_orders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = OperatorPaths(
                root / "ai_quant_config.json",
                root / "strategy_registry.json",
                root / "promoted_strategy.json",
                root / "strategy_specs",
                root / "audit.jsonl",
            )

            result = run_learning_only(paths, _bars())
            config = load_ai_quant_config(paths.ai_config_path)
            records = StrategyRegistry(
                paths.registry_path,
                paths.promoted_path,
                config,
            ).load_records()
            reports = list((paths.spec_dir / "reports").glob("*.json"))
            report = json.loads(reports[0].read_text(encoding="utf-8"))
            resolved = resolve_strategy(
                "paper",
                StrategyArtifactPaths(
                    root,
                    paths.registry_path,
                    paths.promoted_path,
                    paths.spec_dir,
                    paths.audit_log_path,
                    paths.ai_config_path,
                ),
            )

        self.assertEqual(result.submitted_orders, 0)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.accepted_candidates, 1)
        self.assertEqual(result.reasons, ())
        self.assertEqual(records[0].status, StrategyStatus.VALIDATION_PASSED)
        self.assertTrue(config.ai_quant_lab_enabled)
        self.assertTrue(config.self_improvement_enabled)
        self.assertTrue(config.dry_run)
        self.assertFalse(config.live_trading)
        self.assertFalse(config.allow_ai_direct_order)
        self.assertFalse(config.allow_dynamic_code_execution)
        self.assertEqual(config.max_parallel_backtests, 1)
        self.assertEqual(len(reports), 1)
        self.assertEqual(report["strategy_id"], "builtin_trend_following")
        self.assertFalse(report["promoted_to_live"])
        self.assertIn("model_sha256", report)
        self.assertIsInstance(resolved, ResolvedStrategy)

    def test_learning_only_preserves_existing_research_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "ai_quant_config.json"
            config_path.write_text(
                json.dumps({"insane_search_command": ["python", "research.py"]}),
                encoding="utf-8",
            )
            paths = OperatorPaths(
                config_path,
                root / "strategy_registry.json",
                root / "promoted_strategy.json",
                root / "strategy_specs",
                root / "audit.jsonl",
            )

            run_learning_only(paths, _bars())
            config = load_ai_quant_config(config_path)

        self.assertEqual(config.insane_search_command, ("python", "research.py"))

    def test_learning_only_repairs_unsafe_research_guard_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "ai_quant_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "research_provider": "other",
                        "allow_only_insane_search_for_research": False,
                        "disable_research_if_insane_search_unavailable": False,
                    }
                ),
                encoding="utf-8",
            )
            paths = OperatorPaths(
                config_path,
                root / "strategy_registry.json",
                root / "promoted_strategy.json",
                root / "strategy_specs",
                root / "audit.jsonl",
            )

            run_learning_only(paths, _bars())
            config = load_ai_quant_config(config_path)

        self.assertEqual(config.research_provider, "insane_search")
        self.assertTrue(config.allow_only_insane_search_for_research)
        self.assertTrue(config.disable_research_if_insane_search_unavailable)

    def test_learning_without_market_data_fails_without_strategy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = OperatorPaths(root / "config.json", root / "registry.json", root / "promoted.json", root / "specs", root / "audit.jsonl")

            result = run_learning_only(paths, {})

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.accepted_candidates, 0)
        self.assertIn("market_data_missing", result.reasons)

    def test_learning_can_be_cancelled_before_artifact_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = OperatorPaths(root / "config.json", root / "registry.json", root / "promoted.json", root / "specs", root / "audit.jsonl")
            cancellation = LearningCancellation()
            cancellation.cancel()

            result = run_learning_only(paths, _bars(), cancellation=cancellation)

        self.assertEqual(result.status, "cancelled")
        self.assertFalse(paths.registry_path.exists())

    def test_same_data_is_not_trained_twice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = OperatorPaths(root / "config.json", root / "registry.json", root / "promoted.json", root / "specs", root / "audit.jsonl")

            first = run_learning_only(paths, _bars())
            second = run_learning_only(paths, _bars())

        self.assertEqual(first.accepted_candidates, 1)
        self.assertEqual(second.accepted_candidates, 0)
        self.assertIn("data_unchanged", second.reasons)


def _bars():
    bars = []
    price = 100.0
    for index in range(320):
        price *= 1.003
        timestamp = (datetime(2024, 1, 1, 21, tzinfo=timezone.utc) + timedelta(days=index)).isoformat()
        bars.append(PriceBar("QQQ", timestamp, price, price * 1.01, price * 0.99, price, 1_000_000, price - 0.01, price + 0.01))
    return {"QQQ": bars, "AAPL": [PriceBar("AAPL", bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume, bar.bid, bar.ask) for bar in bars]}


if __name__ == "__main__":
    unittest.main()
