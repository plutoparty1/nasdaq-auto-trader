import json
import unittest
from datetime import datetime, timezone

from nasdaq_auto_trader.ai_decision_manager import (
    AIDecisionContext,
    AIDecisionManager,
    AIDecisionResult,
    TradingAgentsRecommendationProvider,
    TradingAgentsRecommendationUnavailableError,
)
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.models import AccountSnapshot


class AIDecisionManagerContractTests(unittest.TestCase):
    def test_manager_accepts_structured_supervisor_decision_without_ai_quantity(self):
        now = datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc)
        provider = _SupervisorProvider(now)
        context = AIDecisionContext(
            candidate_tickers=["NVDA"],
            account=AccountSnapshot(10_000, 10_000, 10_000),
            positions={},
            bars_by_symbol={},
            settings=TradingSettings(order_qty=1, ai_max_order_qty=2),
            now=now,
        )

        result = AIDecisionManager(provider).recommend(context)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.recommendation.ticker, "NVDA")
        self.assertEqual(result.recommendation.order_qty, 1)
        self.assertEqual(result.recommendation.action, "buy")

    def test_context_and_result_are_slotted_and_log_shape_is_stable(self):
        context = AIDecisionContext(
            candidate_tickers=["NVDA"],
            account=AccountSnapshot(10_000, 10_000, 10_000),
            positions={},
            bars_by_symbol={},
            settings=TradingSettings(),
            now=datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
        )
        result = AIDecisionResult("error", "prompt", ["NVDA"], error="bad")

        self.assertFalse(hasattr(context, "__dict__"))
        self.assertFalse(hasattr(result, "__dict__"))
        self.assertEqual(
            result.to_dict(),
            {
                "status": "error",
                "candidate_tickers": ["NVDA"],
                "raw_response": None,
                "parse_success": False,
                "recommendation": None,
                "error": "bad",
                "attempts": 0,
                "prompt": "prompt",
            },
        )

    def test_tradingagents_provider_raises_typed_unavailable_error(self):
        provider = TradingAgentsRecommendationProvider(
            _UnavailableAdvisor(),
            analysis_date="2026-06-26",
        )
        context = AIDecisionContext(
            candidate_tickers=["NVDA"],
            account=AccountSnapshot(10_000, 10_000, 10_000),
            positions={},
            bars_by_symbol={},
            settings=TradingSettings(),
            now=datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
        )

        with self.assertRaisesRegex(
            TradingAgentsRecommendationUnavailableError,
            "package missing",
        ):
            provider.request_ai_recommendation("prompt", context)


class _UnavailableAdvisor:
    def analyze(self, symbol: str, analysis_date: str, asset_type: str):
        return {
            "status": "error",
            "symbol": symbol,
            "analysis_date": analysis_date,
            "asset_type": asset_type,
            "error": "package missing",
        }


class _SupervisorProvider:
    def __init__(self, now):
        self.now = now

    def request_ai_recommendation(self, prompt, context):
        del prompt, context
        return json.dumps(
            {
                "symbol": "NVDA",
                "action": "BUY",
                "confidence": 0.8,
                "target_position_pct": 0.02,
                "signal_timestamp": self.now.isoformat(),
                "model_version": "champion:v1",
                "market_regime": "uptrend",
                "reason_codes": ["signals_aligned"],
                "risk_flags": [],
                "summary": "정량 신호와 계좌 위험을 함께 확인함",
            }
        )


if __name__ == "__main__":
    unittest.main()
