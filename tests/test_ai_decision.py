import unittest
from datetime import datetime, timezone

from tests.ai_decision_fixtures import (
    FakeBroker,
    MultiSymbolMarketData,
    StaticAIProvider,
    StaticAIProviderExhaustedError,
    ai_json,
    compact_strategy,
    uptrend_bars,
)
from nasdaq_auto_trader.ai_decision_manager import AIDecisionContext, AIDecisionManager
from nasdaq_auto_trader.ai_decision_schema import (
    AIDecisionSchemaError,
    AITradeRecommendation,
    parse_ai_trade_recommendation,
)
from nasdaq_auto_trader.ai_trade_guard import guard_ai_recommendation
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import (
    TradingSessionState,
    TradingSettings,
    apply_settings_to_app_config,
)
from nasdaq_auto_trader.engine import TradingEngine
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

    def test_engine_ai_recommend_only_never_submits_order(self):
        settings = TradingSettings(
            ai_ticker_selection_enabled=True,
            ai_order_qty_enabled=True,
            ai_trade_decision_enabled=True,
            ai_recommend_only=True,
            ai_candidate_tickers=["NVDA"],
            order_qty=1,
            max_position_qty=5,
        )
        config = apply_settings_to_app_config(
            AppConfig(mode="dry_run", strategy=compact_strategy()),
            settings,
        )
        broker = FakeBroker()
        engine = TradingEngine(
            config,
            broker=broker,
            market_data=MultiSymbolMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
            trading_settings=settings,
            trading_session_state=TradingSessionState(),
            ai_provider=StaticAIProvider([ai_json()]),
        )

        result = engine.run_once()[0]

        self.assertEqual(result["ai_decision"]["recommendation"]["ticker"], "NVDA")
        self.assertIsNone(result["order"])
        self.assertEqual(result["response"]["reason"], "ai_recommend_only")
        self.assertEqual(broker.orders, [])

    def test_engine_rejects_ai_candidate_outside_user_list(self):
        settings = TradingSettings(
            ai_ticker_selection_enabled=True,
            ai_order_qty_enabled=True,
            ai_trade_decision_enabled=True,
            ai_recommend_only=True,
            ai_candidate_tickers=["NVDA"],
            max_position_qty=5,
            ai_retry_count=0,
        )
        config = apply_settings_to_app_config(
            AppConfig(mode="dry_run", strategy=compact_strategy()),
            settings,
        )
        engine = TradingEngine(
            config,
            broker=FakeBroker(),
            market_data=MultiSymbolMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
            trading_settings=settings,
            trading_session_state=TradingSessionState(),
            ai_provider=StaticAIProvider([ai_json(ticker="AAPL")]),
        )

        result = engine.run_once()[0]

        self.assertEqual(result["response"]["reason"], "ai_recommendation_failed")
        self.assertFalse(result["ai_decision"]["parse_success"])

    def test_engine_rejects_non_finite_ai_confidence_without_crashing(self):
        settings = TradingSettings(
            ai_ticker_selection_enabled=True,
            ai_order_qty_enabled=True,
            ai_trade_decision_enabled=True,
            ai_recommend_only=True,
            ai_candidate_tickers=["NVDA"],
            max_position_qty=5,
            ai_retry_count=0,
        )
        config = apply_settings_to_app_config(
            AppConfig(mode="dry_run", strategy=compact_strategy()),
            settings,
        )
        raw_response = (
            '{"action": "buy", "ticker": "NVDA", "order_qty": 1, '
            '"confidence": NaN, "reason": "r", "risk": "k"}'
        )
        engine = TradingEngine(
            config,
            broker=FakeBroker(),
            market_data=MultiSymbolMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
            trading_settings=settings,
            trading_session_state=TradingSessionState(),
            ai_provider=StaticAIProvider([raw_response]),
        )

        result = engine.run_once()[0]

        self.assertEqual(result["response"]["reason"], "ai_recommendation_failed")
        self.assertFalse(result["ai_decision"]["parse_success"])
        self.assertIn("non-finite JSON number", result["ai_decision"]["error"])

if __name__ == "__main__":
    unittest.main()
