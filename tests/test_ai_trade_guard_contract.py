import unittest
from datetime import datetime, timezone

from nasdaq_auto_trader.ai_decision_schema import AITradeRecommendation
from nasdaq_auto_trader.ai_trade_guard import guard_ai_recommendation
from nasdaq_auto_trader.config_manager import TradingSessionState, TradingSettings
from nasdaq_auto_trader.models import AccountSnapshot


class AITradeGuardContractTests(unittest.TestCase):
    def test_hold_recommendation_returns_slotted_blocked_response(self):
        result = guard_ai_recommendation(
            AITradeRecommendation("hold", "NVDA", 1, 0.9, "reason", "risk"),
            TradingSettings(
                ai_recommend_only=False,
                dry_run=False,
                live_trading=True,
                require_confirm_after_ai=False,
                max_position_qty=5,
            ),
            AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            None,
            TradingSessionState(),
            datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
            "live",
            100,
        )

        self.assertFalse(hasattr(result, "__dict__"))
        self.assertFalse(result.allowed)
        self.assertIsNotNone(result.response)
        self.assertEqual(result.response["status"], "blocked")
        self.assertEqual(result.response["reason"], "ai_hold")
        self.assertEqual(result.response["ai_recommendation"]["action"], "hold")


if __name__ == "__main__":
    unittest.main()
