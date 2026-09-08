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
from nasdaq_auto_trader.learning_strategy_template import candidate_payload
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
        self.assertEqual(result.accepted_candidates, 0)
        self.assertIn("independent_validation_required", result.reasons)
        self.assertEqual(records[0].status, StrategyStatus.REJECTED)
        self.assertFalse(records[0].allowed_for_live)
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
        self.assertEqual(report["promotion_decision"], "rejected")
        self.assertIn("independent_validation_required", report["rejection_reasons"])
        self.assertEqual(report["evidence_scope"], "single_backtest_in_sample")
        self.assertEqual(len(report["missing_advanced_metrics"]), 5)
        self.assertIn("calmar", report["validation_metrics"])
        self.assertIn("annualization_available", report["validation_metrics"])
        self.assertIn("profit_factor_available", report["validation_metrics"])
        self.assertIn("model_sha256", report)
        self.assertNotIsInstance(resolved, ResolvedStrategy)

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

    def test_same_rejected_research_data_is_not_evaluated_twice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = OperatorPaths(root / "config.json", root / "registry.json", root / "promoted.json", root / "specs", root / "audit.jsonl")

            first = run_learning_only(paths, _bars())
            second = run_learning_only(paths, _bars())

        self.assertEqual(first.accepted_candidates, 0)
        self.assertIn("independent_validation_required", first.reasons)
        self.assertEqual(second.accepted_candidates, 0)
        self.assertIn("data_unchanged", second.reasons)

    def test_orphan_report_is_recovered_instead_of_skipping_registry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = OperatorPaths(
                root / "config.json",
                root / "registry.json",
                root / "promoted.json",
                root / "specs",
                root / "audit.jsonl",
            )
            run_learning_only(paths, _bars())
            paths.registry_path.unlink()

            recovered = run_learning_only(paths, _bars())
            records = StrategyRegistry(
                paths.registry_path,
                paths.promoted_path,
                load_ai_quant_config(paths.ai_config_path),
            ).load_records()

        self.assertEqual(recovered.accepted_candidates, 0)
        self.assertIn("independent_validation_required", recovered.reasons)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, StrategyStatus.REJECTED)

    def test_research_preserves_existing_champion_record_and_promoted_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = OperatorPaths(root / "config.json", root / "registry.json", root / "promoted.json", root / "specs", root / "audit.jsonl")
            payload = candidate_payload(_bars())
            record = {
                "strategy_id": payload["strategy_id"],
                "version": payload["version"],
                "status": "champion",
                "manual_approval": True,
                "allowed_for_live": True,
                "research_basis": payload["research_basis"],
            }
            registry_text = json.dumps([record])
            promoted_text = json.dumps({"active_strategy_id": payload["strategy_id"]})
            paths.registry_path.write_text(registry_text, encoding="utf-8")
            paths.promoted_path.write_text(promoted_text, encoding="utf-8")

            result = run_learning_only(paths, _bars())

            self.assertEqual(paths.registry_path.read_text(encoding="utf-8"), registry_text)
            self.assertEqual(paths.promoted_path.read_text(encoding="utf-8"), promoted_text)
        self.assertEqual(result.accepted_candidates, 0)
        self.assertIn("existing_strategy_record_preserved", result.reasons)


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
