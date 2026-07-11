import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.paper_shadow import (
    ActualExecution,
    ExpectedExecution,
    PaperShadowEngine,
    PaperShadowLedger,
    PaperShadowRequest,
    analyze_post_trade_feedback,
    evaluate_stage_readiness,
)
from nasdaq_auto_trader.ai_quant_lab.backtest_engine import BacktestEngine
from nasdaq_auto_trader.ai_quant_lab.insane_search_research import InsaneSearchResearchService
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.scoring_engine import ScoringEngine
from nasdaq_auto_trader.ai_quant_lab.self_improvement_loop import SelfImprovementLoop
from nasdaq_auto_trader.ai_quant_lab.strategy_factory import AIStrategyFactory
from nasdaq_auto_trader.ai_quant_lab.validation_engine import ValidationEngine
from tests.ai_quant_fixtures import FakeRunner, bars, valid_spec_payload
from nasdaq_auto_trader.execution.position_sizer import PortfolioState
from nasdaq_auto_trader.strategies.base_strategy import TargetPosition


class AIQuantPaperShadowTests(unittest.TestCase):
    def test_paper_trading_creates_virtual_fill_with_costs_and_no_order_api(self):
        audit = NullAuditLogger()
        request = PaperShadowRequest(
            strategy_id="strategy-1",
            strategy_version="v1",
            mode="paper",
            targets=(
                TargetPosition("QQQ", "buy", 1.0, 1.0, 100.0, 99.0, "strategy-1"),
            ),
            portfolio=PortfolioState(100_000, 100_000, {}, 0),
            market_prices={"QQQ": 100.0},
            as_of="2026-06-30T20:00:00+09:00",
        )

        with (
            patch(
                "nasdaq_auto_trader.broker.OrderRequest",
                side_effect=AssertionError("paper shadow must not build broker orders"),
            ),
            patch(
                "nasdaq_auto_trader.broker.DryRunBroker.submit_order",
                side_effect=AssertionError("paper shadow must not submit broker orders"),
            ),
            patch(
                "nasdaq_auto_trader.execution.order_executor.OrderExecutor.submit_after_risk_guard",
                side_effect=AssertionError("paper shadow must not use the order executor"),
            ),
        ):
            result = PaperShadowEngine(
                AIQuantConfig(max_order_notional=1_000, commission_bps=1, slippage_bps=5),
                audit,
            ).run(request)

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.fills), 1)
        self.assertGreater(result.fills[0].fill_price, 100.0)
        self.assertEqual(result.submitted_orders, 0)
        self.assertIn("paper_signal_generated", [event.event_type for event in audit.events])

    def test_paper_shadow_blocks_unsupported_side_without_fill(self):
        result = PaperShadowEngine(AIQuantConfig(max_order_notional=1_000)).run(
            PaperShadowRequest(
                strategy_id="strategy-1",
                strategy_version="v1",
                mode="paper",
                targets=(
                    TargetPosition("QQQ", "hold", 1.0, 1.0, 100.0, 99.0, "strategy-1"),
                ),
                portfolio=PortfolioState(100_000, 100_000, {}, 0),
                market_prices={"QQQ": 100.0},
                as_of="2026-06-30T20:00:00+09:00",
            )
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.fills, ())
        self.assertEqual(result.submitted_orders, 0)
        self.assertIn("unsupported_side", result.blocked_reasons)

    def test_shadow_live_cannot_be_promoted_before_minimum_duration(self):
        readiness = evaluate_stage_readiness(
            mode="shadow",
            observed_days=9,
            result_status="completed",
            config=AIQuantConfig(min_shadow_live_days=10),
        )

        self.assertFalse(readiness.allowed)
        self.assertEqual(readiness.next_status, "shadow_live")
        self.assertIn("min_shadow_live_days_not_met", readiness.reasons)

    def test_post_trade_feedback_calculates_slippage_and_failures(self):
        feedback = analyze_post_trade_feedback(
            expected=(
                ExpectedExecution("strategy-1", "QQQ", "buy", 2, 100.0),
                ExpectedExecution("strategy-1", "AAPL", "buy", 1, 200.0),
                ExpectedExecution("strategy-1", "MSFT", "hold", 1, 300.0),
            ),
            actual=(
                ActualExecution("strategy-1", "QQQ", "buy", 2, 101.0, 0.25, "filled"),
                ActualExecution("strategy-1", "AAPL", "buy", 0, 0.0, 0.0, "rejected"),
                ActualExecution("strategy-1", "MSFT", "hold", 1, 300.0, 0.0, "filled"),
            ),
        )

        self.assertEqual(feedback.expected_orders, 3)
        self.assertEqual(feedback.failed_orders, 2)
        self.assertGreater(feedback.average_slippage_bps, 0)
        self.assertIn("execution_failures_detected", feedback.failure_reasons)

    def test_ledger_persists_equity_curve_feedback_and_audit_event(self):
        audit = NullAuditLogger()
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PaperShadowLedger(Path(temp_dir) / "paper.jsonl", audit)
            result = PaperShadowEngine(AIQuantConfig(), audit).run(
                PaperShadowRequest(
                    strategy_id="strategy-1",
                    strategy_version="v1",
                    mode="paper",
                    targets=(),
                    portfolio=PortfolioState(100_000, 100_000, {}, 0),
                    market_prices={},
                    as_of="2026-06-30T20:00:00+09:00",
                )
            )
            saved = ledger.append(result)

        self.assertTrue(saved)
        self.assertIn("paper_result_recorded", [event.event_type for event in audit.events])

    def test_self_improvement_prompt_includes_post_trade_feedback(self):
        class CapturingProvider:
            def __init__(self) -> None:
                self.prompt = ""

            def request_strategy_specs(self, prompt, context):
                del context
                self.prompt = prompt
                return ()

        provider = CapturingProvider()
        feedback = analyze_post_trade_feedback(
            expected=(ExpectedExecution("strategy-1", "QQQ", "buy", 1, 100.0),),
            actual=(ActualExecution("strategy-1", "QQQ", "buy", 1, 101.0, 0.5, "filled"),),
        )
        config = AIQuantConfig(ai_quant_lab_enabled=True, self_improvement_enabled=True)
        with tempfile.TemporaryDirectory() as temp_dir:
            loop = SelfImprovementLoop(
                config,
                InsaneSearchResearchService(config=config, runner=FakeRunner()),
                AIStrategyFactory(provider),
                BacktestEngine(config),
                ValidationEngine(),
                ScoringEngine(),
                StrategyRegistry(Path(temp_dir) / "registry.json", Path(temp_dir) / "promoted.json", config),
            )
            loop.run_once({"QQQ": bars("QQQ")}, post_trade_feedback=feedback)

        self.assertIn("Post-trade feedback", provider.prompt)
        self.assertIn("average_slippage_bps", provider.prompt)


if __name__ == "__main__":
    unittest.main()
