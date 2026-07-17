import unittest
from datetime import datetime, timezone

from tests.ai_decision_fixtures import (
    StaticAIProvider,
    StaticAIProviderExhaustedError,
    ai_json,
    uptrend_bars,
)
from nasdaq_auto_trader.ai_decision_manager import AIDecisionContext, AIDecisionManager
from nasdaq_auto_trader.ai_decision_schema import (
    AIDecisionSchemaError,
    AITradeRecommendation,
    parse_ai_trade_recommendation,
)
from nasdaq_auto_trader.ai_trade_guard import guard_ai_recommendation
from nasdaq_auto_trader.config_manager import (
    TradingSessionState,
    TradingSettings,
)
from nasdaq_auto_trader.models import AccountSnapshot, Position


class AIDecisionTests(unittest.TestCase):
    def test_static_ai_provider_raises_typed_error_when_responses_are_exhausted(self):
        provider = StaticAIProvider([])

        with self.assertRaises(StaticAIProviderExhaustedError):
            provider.request_ai_recommendation("prompt", {})

    def test_parse_rejects_non_json_and_outside_candidate(self):
        with self.assertRaises(AIDecisionSchemaError):
            parse_ai_trade_recommendation("not-json", ["NVDA"])
        with self.assertRaises(AIDecisionSchemaError):
            parse_ai_trade_recommendation(ai_json(ticker="AAPL"), ["NVDA"])

    def test_parse_rejects_non_finite_confidence(self):
        raw_response = (
            '{"action": "buy", "ticker": "NVDA", "order_qty": 1, '
            '"confidence": NaN, "reason": "r", "risk": "k"}'
        )

        with self.assertRaisesRegex(AIDecisionSchemaError, "non-finite JSON number"):
            parse_ai_trade_recommendation(raw_response, ["NVDA"])

    def test_guard_blocks_recommend_only_low_confidence_and_oversized_qty(self):
        account = AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000)
        now = datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc)

        recommend_only = guard_ai_recommendation(
            AITradeRecommendation("buy", "NVDA", 1, 0.9, "reason", "risk"),
            TradingSettings(
                ai_recommend_only=True,
                dry_run=False,
                live_trading=True,
                require_confirm_after_ai=False,
                max_position_qty=5,
            ),
            account,
            None,
            TradingSessionState(),
            now,
            "live",
            100,
        )
        low_confidence = guard_ai_recommendation(
            AITradeRecommendation("buy", "NVDA", 1, 0.2, "reason", "risk"),
            TradingSettings(
                ai_recommend_only=False,
                dry_run=False,
                live_trading=True,
                require_confirm_after_ai=False,
                max_position_qty=5,
            ),
            account,
            None,
            TradingSessionState(),
            now,
            "live",
            100,
        )
        oversized = guard_ai_recommendation(
            AITradeRecommendation("buy", "NVDA", 3, 0.9, "reason", "risk"),
            TradingSettings(
                ai_recommend_only=False,
                dry_run=False,
                live_trading=True,
                require_confirm_after_ai=False,
                ai_max_order_qty=1,
                max_position_qty=5,
            ),
            account,
            None,
            TradingSessionState(),
            now,
            "live",
            100,
        )

        self.assertEqual(recommend_only.response["reason"], "ai_recommend_only")
        self.assertEqual(low_confidence.response["reason"], "ai_confidence_below_minimum")
        self.assertEqual(oversized.response["reason"], "ai_order_qty_exceeds_ai_max")

    def test_guard_blocks_sell_only_additional_buy_and_oversell(self):
        account = AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000)
        now = datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc)
        base = {
            "ai_recommend_only": False,
            "dry_run": False,
            "live_trading": True,
            "require_confirm_after_ai": False,
            "ai_max_order_qty": 5,
            "max_position_qty": 5,
        }

        sell_only = guard_ai_recommendation(
            AITradeRecommendation("buy", "NVDA", 1, 0.9, "reason", "risk"),
            TradingSettings(**base, sell_only=True),
            account,
            None,
            TradingSessionState(),
            now,
            "live",
            100,
        )
        additional_buy = guard_ai_recommendation(
            AITradeRecommendation("buy", "NVDA", 1, 0.9, "reason", "risk"),
            TradingSettings(**base, allow_additional_buy=False),
            account,
            Position("NVDA", 1, 100, 100),
            TradingSessionState(),
            now,
            "live",
            100,
        )
        oversell = guard_ai_recommendation(
            AITradeRecommendation("sell", "NVDA", 3, 0.9, "reason", "risk"),
            TradingSettings(**base),
            account,
            Position("NVDA", 1, 100, 100),
            TradingSessionState(),
            now,
            "live",
            100,
        )

        self.assertEqual(sell_only.response["reason"], "sell_only_mode")
        self.assertEqual(additional_buy.response["reason"], "additional_buy_disabled")
        self.assertEqual(oversell.response["reason"], "sell_qty_exceeds_position")

    def test_guard_blocks_ai_buy_when_cash_is_below_order_value(self):
        settings = TradingSettings(
            ai_recommend_only=False,
            dry_run=False,
            live_trading=True,
            require_confirm_after_ai=False,
            ai_max_order_qty=5,
            max_position_qty=5,
        )

        result = guard_ai_recommendation(
            AITradeRecommendation("buy", "NVDA", 1, 0.9, "reason", "risk"),
            settings,
            AccountSnapshot(cash=10, equity=1_000, buying_power=1_000),
            None,
            TradingSessionState(),
            datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
            "live",
            500,
        )

        self.assertEqual(result.response["reason"], "deposited_cash_insufficient")
        self.assertIsNone(result.order)

    def test_manager_retries_and_returns_parse_error_without_order(self):
        manager = AIDecisionManager(StaticAIProvider(["not-json"]))
        context = AIDecisionContext(
            candidate_tickers=["NVDA"],
            account=AccountSnapshot(cash=1000, equity=1000, buying_power=1000),
            positions={},
            bars_by_symbol={"NVDA": uptrend_bars("NVDA")},
            settings=TradingSettings(ai_retry_count=0),
            now=datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
        )

        result = manager.recommend(context)

        self.assertEqual(result.status, "error")
        self.assertFalse(result.parse_success)
        self.assertIn("valid JSON", result.error)

if __name__ == "__main__":
    unittest.main()
