import json
import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.config import load_ai_quant_config
from nasdaq_auto_trader.ai_quant_lab.operator_models import OperatorPaths
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.registry_models import StrategyStatus
from nasdaq_auto_trader.learning_runner import run_learning_only


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

            result = run_learning_only(paths)
            config = load_ai_quant_config(paths.ai_config_path)
            records = StrategyRegistry(
                paths.registry_path,
                paths.promoted_path,
                config,
            ).load_records()

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

            run_learning_only(paths)
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

            run_learning_only(paths)
            config = load_ai_quant_config(config_path)

        self.assertEqual(config.research_provider, "insane_search")
        self.assertTrue(config.allow_only_insane_search_for_research)
        self.assertTrue(config.disable_research_if_insane_search_unavailable)


if __name__ == "__main__":
    unittest.main()
