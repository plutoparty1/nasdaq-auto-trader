import unittest
from datetime import datetime, timezone

from nasdaq_auto_trader.ai_decision_manager import (
    AIDecisionContext,
    AIDecisionResult,
    TradingAgentsRecommendationProvider,
    TradingAgentsRecommendationUnavailableError,
)
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.models import AccountSnapshot


class AIDecisionManagerContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
