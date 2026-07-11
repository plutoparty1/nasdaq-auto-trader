import builtins
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from tests.ai_quant_fixtures import (
    FakeBroker,
    FakeLiveMarketData,
    FakeRunner,
    FakeSpecProvider,
    MemorySpecStore,
    bars,
    fake_backtest_result,
    fake_validation_result,
    promoted_payload,
    valid_spec,
    valid_spec_payload,
)
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.ai_quant_lab.backtest_engine import BacktestEngine
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig, validate_ai_quant_config
from nasdaq_auto_trader.ai_quant_lab.insane_search_research import (
    InsaneSearchResearchService,
)
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry, StrategyStatus
from nasdaq_auto_trader.ai_quant_lab.scoring_engine import ScoringEngine
from nasdaq_auto_trader.ai_quant_lab.self_improvement_loop import (
    SelfImprovementLoop,
)
from nasdaq_auto_trader.ai_quant_lab.strategy_factory import AIStrategyFactory
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import (
    ResearchBasis,
    parse_strategy_spec_json,
    validate_strategy_spec,
)
from nasdaq_auto_trader.ai_quant_lab.validation_engine import ValidationEngine
from nasdaq_auto_trader.execution.kill_switch import KillSwitch, KillSwitchState
from nasdaq_auto_trader.execution.live_engine import LiveEngine
from nasdaq_auto_trader.execution.position_sizer import PortfolioState, PositionSizer, SizingRequest
from nasdaq_auto_trader.execution.risk_guard import (
    OrderIntent,
    RiskGuard,
    RiskGuardContext,
)
from nasdaq_auto_trader.quant_data.universe import UniverseBuilder, UniverseCandidate
from nasdaq_auto_trader.strategies.base_strategy import TargetPosition


class AIQuantLabTests(unittest.TestCase):
    def test_default_config_is_fail_closed_and_requires_insane_search(self):
        config = AIQuantConfig()
        validation = validate_ai_quant_config(config)

        self.assertTrue(validation.valid)
        self.assertFalse(config.live_trading)
        self.assertTrue(config.dry_run)
        self.assertFalse(config.allow_ai_direct_order)
        self.assertFalse(config.allow_dynamic_code_execution)
        self.assertEqual(config.research_provider, "insane_search")

    def test_config_rejects_non_insane_research_provider(self):
        config = AIQuantConfig(research_provider="generic_web")

        validation = validate_ai_quant_config(config)

        self.assertFalse(validation.valid)
        self.assertIn("research_provider_must_be_insane_search", validation.reasons)

    def test_research_service_fails_closed_when_insane_search_unavailable(self):
        runner = FakeRunner(available=False)
        audit = NullAuditLogger()
        service = InsaneSearchResearchService(runner=runner, audit_logger=audit)

        result = service.run_quant_research("walk forward validation")

        self.assertFalse(result.usable)
        self.assertEqual(result.failure_reason, "insane_search_unavailable")
        self.assertEqual(runner.calls, [])
        self.assertIn("insane_search_failed", [event.event_type for event in audit.events])

    def test_strategy_schema_rejects_markdown_unknown_signal_and_missing_sources(self):
        markdown = parse_strategy_spec_json("```json\n{}\n```")
        bad_signal = valid_spec_payload()
        bad_signal["signals"] = [{"type": "magic_alpha", "weight": 1.0}]
        missing_sources = valid_spec_payload()
        missing_sources["research_basis"] = {"provider": "insane_search", "research_ids": ["r1"], "source_ids": []}

        self.assertFalse(markdown.valid)
        self.assertIn("strategy_spec_must_be_json_only", markdown.reasons)
        self.assertIn("signal_type_not_allowed", validate_strategy_spec(bad_signal).reasons)
        self.assertIn("research_basis_source_ids_required", validate_strategy_spec(missing_sources).reasons)

    def test_strategy_factory_accepts_json_only_and_does_not_use_eval_exec(self):
        context = (
            InsaneSearchResearchService(runner=FakeRunner())
            .build_research_context_for_strategy_generation()
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            marker = Path(temp_dir) / "eval-exec-marker.txt"
            executable_candidate = (
                "__import__('pathlib').Path("
                f"{str(marker)!r}"
                ").write_text('owned', encoding='utf-8')"
            )
            provider = FakeSpecProvider(
                [json.dumps(valid_spec_payload()), executable_candidate]
            )
            factory = AIStrategyFactory(provider)

            result = factory.generate_candidates(context, 10)

        self.assertEqual(len(result.accepted), 1)
        self.assertIn("strategy_spec_must_be_json_only", result.rejected_reasons)
        self.assertFalse(marker.exists())

    def test_universe_filters_stale_halted_liquidity_and_spread(self):
        now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
        candidates = [
            UniverseCandidate("GOOD", last_price=10, bid=9.99, ask=10.01, avg_volume_20d=1_000_000, dollar_volume=10_000_000, updated_at=now),
            UniverseCandidate("HALT", halted=True, last_price=10, bid=9.99, ask=10.01, avg_volume_20d=1_000_000, dollar_volume=10_000_000, updated_at=now),
            UniverseCandidate("STALE", last_price=10, bid=9.99, ask=10.01, avg_volume_20d=1_000_000, dollar_volume=10_000_000, updated_at=now - timedelta(seconds=120)),
            UniverseCandidate("WIDE", last_price=10, bid=9.50, ask=10.50, avg_volume_20d=1_000_000, dollar_volume=10_000_000, updated_at=now),
            UniverseCandidate("LOW", last_price=10, bid=9.99, ask=10.01, avg_volume_20d=10, dollar_volume=100, updated_at=now),
        ]

        selection = UniverseBuilder().filter(candidates, now)
        rejected = {item.symbol: item.reasons for item in selection.rejected}

        self.assertEqual([item.symbol for item in selection.selected], ["GOOD"])
        self.assertIn("halted", rejected["HALT"])
        self.assertIn("stale_data", rejected["STALE"])
        self.assertIn("spread_too_wide", rejected["WIDE"])
        self.assertIn("liquidity_too_low", rejected["LOW"])

    def test_position_sizer_blocks_cash_exposure_and_oversell(self):
        target = TargetPosition("QQQ", "buy", 0.9, 0.9, 100.0, 98.0, "s1")
        sizer = PositionSizer(AIQuantConfig(max_order_notional=1000))
        portfolio = PortfolioState(10_000, 50, {}, 0)
        blocked = sizer.calculate(SizingRequest(target, portfolio, 100.0))
        sell = TargetPosition("QQQ", "sell", 1.0, 10.0, 100.0, 99.0, "s1")
        oversell = sizer.calculate(SizingRequest(sell, PortfolioState(10_000, 10_000, {"QQQ": 0}, 0), 100.0))

        self.assertEqual(blocked.blocked_reason, "sizing_limits_block_order")
        self.assertEqual(oversell.blocked_reason, "sell_position_missing")

    def test_risk_guard_blocks_defaults_and_audit_failures(self):
        intent = OrderIntent("s1", "QQQ", "buy", 1, 100.0, 100.0)
        guard = RiskGuard()
        default_result = guard.check(RiskGuardContext(AIQuantConfig(), intent, None))
        audit = NullAuditLogger()
        audit.fail_writes = True
        live_config = AIQuantConfig(live_trading=True, dry_run=False, controlled_live_enabled=True)
        promoted = promoted_payload("s1")
        audit_result = RiskGuard(audit).check(
            RiskGuardContext(live_config, intent, promoted, available_cash=1000)
        )

        self.assertEqual(default_result.block_reason, "live_trading_disabled")
        self.assertEqual(audit_result.block_reason, "audit_log_write_failed")

    def test_registry_blocks_champion_jump_and_live_without_manual_approval(self):
        spec = valid_spec()
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = StrategyRegistry(Path(temp_dir) / "registry.json", Path(temp_dir) / "promoted.json")
            score = ScoringEngine().score(
                fake_backtest_result(spec.strategy_id),
                fake_validation_result(),
            )
            decision = registry.evaluate_promotion(spec, score, StrategyStatus.CHAMPION)
            record = registry.register_schema_validated(spec)
            champion = registry.lock_champion(record, {"max_single_position_pct": 0.05})

        self.assertFalse(decision.allowed)
        self.assertIn("paper_and_shadow_period_required", decision.reasons)
        self.assertFalse(champion.allowed)
        self.assertIn("record_not_champion", champion.reasons)

    def test_registry_rollback_rewrites_promoted_strategy_to_no_trade(self):
        audit = NullAuditLogger()
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = StrategyRegistry(
                Path(temp_dir) / "registry.json",
                Path(temp_dir) / "promoted.json",
                audit_logger=audit,
            )
            registry.promoted_path.write_text(
                json.dumps(promoted_payload("s1")),
                encoding="utf-8",
            )

            decision = registry.rollback_to_no_trade("strategy_drawdown_limit_exceeded")
            promoted = registry.load_promoted_strategy()
            records = registry.load_records()

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.target_status, StrategyStatus.ROLLBACK)
        self.assertEqual(promoted["status"], "rollback")
        self.assertEqual(promoted["mode"], "no_trade")
        self.assertFalse(promoted["allowed_for_live"])
        self.assertEqual(promoted["rollback_reason"], "strategy_drawdown_limit_exceeded")
        self.assertEqual(records[0].status, StrategyStatus.ROLLBACK)
        self.assertEqual(records[0].research_basis, ResearchBasis("insane_search", ("research-1",), ("source-1",), ""))
        self.assertIn("rollback_triggered", [event.event_type for event in audit.events])

    def test_self_improvement_loop_does_not_call_factory_when_research_unavailable(self):
        config = AIQuantConfig(ai_quant_lab_enabled=True, self_improvement_enabled=True)
        provider = FakeSpecProvider([json.dumps(valid_spec_payload())])
        with tempfile.TemporaryDirectory() as temp_dir:
            loop = SelfImprovementLoop(
                config,
                InsaneSearchResearchService(config=config, runner=FakeRunner(available=False)),
                AIStrategyFactory(provider),
                BacktestEngine(config),
                ValidationEngine(),
                ScoringEngine(),
                StrategyRegistry(Path(temp_dir) / "registry.json", Path(temp_dir) / "promoted.json", config),
            )
            result = loop.run_once({"QQQ": bars("QQQ")})

        self.assertEqual(result.status, "aborted")
        self.assertIn("insane_search_unavailable", result.reasons)
        self.assertEqual(provider.calls, 0)

    def test_live_engine_uses_promoted_strategy_only_and_no_research_imports(self):
        spec = valid_spec()
        broker = FakeBroker()
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = StrategyRegistry(
                Path(temp_dir) / "registry.json",
                Path(temp_dir) / "promoted.json",
                AIQuantConfig(live_trading=True, dry_run=False, controlled_live_enabled=True),
            )
            registry.promoted_path.write_text(json.dumps(promoted_payload(spec.strategy_id)), encoding="utf-8")
            engine = LiveEngine(
                registry,
                MemorySpecStore(spec),
                FakeLiveMarketData({"QQQ": bars("QQQ"), "AAPL": bars("AAPL")}, PortfolioState(100_000, 100_000, {}, 0)),
                broker,
            )
            blocked_modules = (
                "nasdaq_auto_trader.ai_quant_lab.insane_search_research",
                "nasdaq_auto_trader.ai_quant_lab.strategy_factory",
            )
            blocked_fromlist = {
                "AIStrategyFactory",
                "InsaneSearchResearchService",
                "insane_search_research",
                "strategy_factory",
            }
            original_import = builtins.__import__

            def import_without_research(name, globals=None, locals=None, fromlist=(), level=0):
                if name in blocked_modules or (
                    name == "nasdaq_auto_trader.ai_quant_lab"
                    and any(item in blocked_fromlist for item in fromlist or ())
                ):
                    raise AssertionError(f"live engine imported research dependency: {name}")
                return original_import(name, globals, locals, fromlist, level)

            with patch("builtins.__import__", side_effect=import_without_research):
                result = engine.run_cycle(KillSwitchState())

        self.assertEqual(result.submitted_orders, 0)
        self.assertIn("audit_logger_not_durable", result.blocked_reasons)
        self.assertEqual(broker.orders, [])

    def test_kill_switch_blocks_live_engine_order(self):
        kill = KillSwitch().evaluate(KillSwitchState(manual_kill_switch=True))

        self.assertTrue(kill.active)
        self.assertIn("manual_kill_switch", kill.reasons)

if __name__ == "__main__":
    unittest.main()
