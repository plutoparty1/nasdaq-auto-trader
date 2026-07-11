import json
import tempfile
import unittest
from pathlib import Path

from tests.ai_quant_fixtures import (
    FakeLiveMarketData,
    FakeSpecProvider,
    MemorySpecStore,
    bars,
    promoted_payload,
    valid_spec,
    valid_spec_payload,
)
from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditLogger, NullAuditLogger
from nasdaq_auto_trader.ai_quant_lab.config import (
    AIQuantConfig,
    live_order_block_reason,
    load_ai_quant_config,
    validate_ai_quant_config,
)
from nasdaq_auto_trader.ai_quant_lab.insane_search_research import (
    InsaneSearchResearchService,
    ResearchResult,
    SourceMetadata,
)
from nasdaq_auto_trader.ai_quant_lab.registry import (
    StrategyRecord,
    StrategyRegistry,
    StrategyStatus,
)
from nasdaq_auto_trader.ai_quant_lab.scoring_engine import StrategyScore
from nasdaq_auto_trader.ai_quant_lab.strategy_factory import AIStrategyFactory
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import (
    ResearchBasis,
    parse_strategy_spec_json,
    validate_strategy_spec,
)
from nasdaq_auto_trader.execution.kill_switch import KillSwitchState
from nasdaq_auto_trader.execution.live_engine import LiveEngine
from nasdaq_auto_trader.execution.position_sizer import PortfolioState
from nasdaq_auto_trader.execution.risk_guard import RiskGuard


class EvilResearchRunner:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def run(self, query):
        self.calls += 1
        return ResearchResult(
            research_id=f"../evil/../../research-{self.calls}",
            provider="insane_search",
            query=query,
            created_at="2026-06-30T00:00:00+09:00",
            sources=(SourceMetadata(f"source-{self.calls}", "title", "https://example.test", "", ""),),
            summary="summary",
            usable=True,
            failure_reason="",
        )


class RejectingBroker:
    def __init__(self):
        self.orders = []

    def submit_order(self, intent):
        self.orders.append(intent)
        return {"status": "rejected", "reason": "broker_rejected"}


class AIQuantSecurityTests(unittest.TestCase):
    def test_malformed_config_is_parsed_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "live_trading": "true",
                        "dry_run": False,
                        "controlled_live_enabled": True,
                    }
                ),
                encoding="utf-8",
            )

            config = load_ai_quant_config(config_path)

        self.assertTrue(validate_ai_quant_config(config).valid)
        self.assertEqual(live_order_block_reason(config), "live_trading_disabled")

    def test_runtime_type_bypass_is_rejected_before_live_ordering(self):
        config = AIQuantConfig(
            **{"live_trading": "true", "dry_run": False, "controlled_live_enabled": True}
        )

        validation = validate_ai_quant_config(config)

        self.assertFalse(validation.valid)
        self.assertIn("live_trading_must_be_bool", validation.reasons)
        self.assertEqual(live_order_block_reason(config), "ai_quant_config_invalid")

    def test_strategy_schema_reports_bad_numeric_types_without_raising(self):
        payload = valid_spec_payload()
        payload["entry_rule"]["threshold"] = "bad"
        payload["entry_rule"]["top_n"] = "bad"
        payload["exit_rule"]["stop_loss_atr_multiple"] = "bad"

        validation = validate_strategy_spec(payload)

        self.assertFalse(validation.valid)
        self.assertIn("entry_rule_threshold_out_of_range", validation.reasons)
        self.assertIn("entry_rule_top_n_must_be_positive", validation.reasons)
        self.assertIn("stop_loss_atr_multiple_must_be_positive", validation.reasons)

    def test_ai_artifacts_are_sanitized_inside_output_directories(self):
        payload = valid_spec_payload()
        payload["strategy_id"] = "../evil"
        payload["version"] = "v1/../../x"
        audit = NullAuditLogger()
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            spec_dir = base / "specs"
            research_dir = base / "research"
            service = InsaneSearchResearchService(
                config=AIQuantConfig(),
                runner=EvilResearchRunner(),
                result_dir=research_dir,
            )

            research = service.run_quant_research("query")
            context = service.build_research_context_for_strategy_generation()
            payload["research_basis"]["research_ids"] = [context.research_ids[0]]
            payload["research_basis"]["source_ids"] = [context.source_ids[0]]
            factory = AIStrategyFactory(
                FakeSpecProvider([json.dumps(payload)]),
                audit_logger=audit,
                output_dir=spec_dir,
            )
            result = factory.generate_candidates(context, 1)

            spec_files = tuple(spec_dir.iterdir())
            research_files = tuple(research_dir.iterdir())

        self.assertTrue(research.usable)
        self.assertEqual(len(result.accepted), 1)
        self.assertEqual(len(spec_files), 1)
        self.assertGreaterEqual(len(research_files), 1)
        self.assertTrue(all(path.parent == spec_dir for path in spec_files))
        self.assertTrue(all(path.parent == research_dir for path in research_files))

    def test_audit_failure_blocks_strategy_generation_and_promotion(self):
        audit = NullAuditLogger()
        audit.fail_writes = True
        context = InsaneSearchResearchService(runner=EvilResearchRunner()).build_research_context_for_strategy_generation()
        factory = AIStrategyFactory(
            FakeSpecProvider([json.dumps(valid_spec_payload())]),
            audit_logger=audit,
        )
        score = StrategyScore(0.9, {}, (), True)
        spec = valid_spec()
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = StrategyRegistry(
                Path(temp_dir) / "registry.json",
                Path(temp_dir) / "promoted.json",
                audit_logger=audit,
            )

            factory_result = factory.generate_candidates(context, 1)
            promotion = registry.evaluate_promotion(spec, score)

        self.assertEqual(factory_result.accepted, ())
        self.assertIn("audit_log_write_failed", factory_result.rejected_reasons)
        self.assertFalse(promotion.allowed)
        self.assertIn("audit_log_write_failed", promotion.reasons)

    def test_audit_failure_blocks_champion_lock_file_write(self):
        audit = NullAuditLogger()
        audit.fail_writes = True
        record = StrategyRecord(
            "s1",
            "v1",
            StrategyStatus.CHAMPION,
            True,
            True,
            ResearchBasis("insane_search", ("research-1",), ("source-1",), ""),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            promoted_path = Path(temp_dir) / "promoted.json"
            registry = StrategyRegistry(
                Path(temp_dir) / "registry.json",
                promoted_path,
                audit_logger=audit,
            )

            decision = registry.lock_champion(record, {"max_single_position_pct": 0.05})

            self.assertFalse(promoted_path.exists())

        self.assertFalse(decision.allowed)
        self.assertIn("audit_log_write_failed", decision.reasons)

    def test_corrupt_registry_and_promoted_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "registry.json"
            promoted_path = Path(temp_dir) / "promoted.json"
            registry_path.write_text(
                json.dumps([{"status": "invalid", "research_basis": {}}]),
                encoding="utf-8",
            )
            promoted_path.write_text("{", encoding="utf-8")
            registry = StrategyRegistry(registry_path, promoted_path)

            records = registry.load_records()
            promoted = registry.load_promoted_strategy()

        self.assertEqual(records, ())
        self.assertIsNone(promoted)

    def test_broker_rejected_response_is_not_counted_as_submitted(self):
        spec = valid_spec()
        broker = RejectingBroker()
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = StrategyRegistry(
                Path(temp_dir) / "registry.json",
                Path(temp_dir) / "promoted.json",
                AIQuantConfig(live_trading=True, dry_run=False, controlled_live_enabled=True),
            )
            registry.promoted_path.write_text(
                json.dumps(promoted_payload(spec.strategy_id)),
                encoding="utf-8",
            )
            engine = LiveEngine(
                registry,
                MemorySpecStore(spec),
                FakeLiveMarketData(
                    {"QQQ": bars("QQQ"), "AAPL": bars("AAPL")},
                    PortfolioState(100_000, 100_000, {}, 0),
                ),
                broker,
                risk_guard=RiskGuard(AuditLogger(Path(temp_dir) / "audit.jsonl")),
            )

            result = engine.run_cycle(KillSwitchState())

        self.assertEqual(len(broker.orders), 2)
        self.assertEqual(result.submitted_orders, 0)
        self.assertEqual(result.blocked_reasons, ("broker_rejected", "broker_rejected"))

    def test_default_risk_guard_blocks_live_orders_without_durable_audit(self):
        spec = valid_spec()
        broker = RejectingBroker()
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = StrategyRegistry(
                Path(temp_dir) / "registry.json",
                Path(temp_dir) / "promoted.json",
                AIQuantConfig(live_trading=True, dry_run=False, controlled_live_enabled=True),
            )
            registry.promoted_path.write_text(
                json.dumps(promoted_payload(spec.strategy_id)),
                encoding="utf-8",
            )
            engine = LiveEngine(
                registry,
                MemorySpecStore(spec),
                FakeLiveMarketData(
                    {"QQQ": bars("QQQ"), "AAPL": bars("AAPL")},
                    PortfolioState(100_000, 100_000, {}, 0),
                ),
                broker,
            )

            result = engine.run_cycle(KillSwitchState())

        self.assertEqual(broker.orders, [])
        self.assertEqual(result.submitted_orders, 0)
        self.assertEqual(result.blocked_reasons, ("audit_logger_not_durable", "audit_logger_not_durable"))


if __name__ == "__main__":
    unittest.main()
