import unittest
from datetime import datetime, timezone

from tests.ai_decision_fixtures import (
    FakeBroker,
    MultiSymbolMarketData,
    StaticAIProvider,
    ai_json,
    compact_strategy,
)
from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import (
    TradingSessionState,
    TradingSettings,
    apply_settings_to_app_config,
)
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot


class AIEngineDecisionTests(unittest.TestCase):
    def test_engine_ai_auto_order_is_blocked_even_after_all_legacy_gates_pass(self):
        settings = TradingSettings(
            live_trading=True,
            dry_run=False,
            require_confirm_before_buy=False,
            require_confirm_after_ai=False,
            ai_ticker_selection_enabled=True,
            ai_order_qty_enabled=True,
            ai_trade_decision_enabled=True,
            ai_recommend_only=False,
            ai_candidate_tickers=["NVDA"],
            order_qty=1,
            max_position_qty=5,
        )
        config = apply_settings_to_app_config(
            AppConfig(
                mode="dry_run",
                allow_live_trading=False,
                live_environment_authorized=True,
                regular_market_hours_only=True,
                alpaca=AlpacaCredentials("key", "secret", paper=False),
                strategy=compact_strategy(),
            ),
            settings,
        )
        broker = FakeBroker()
        engine = TradingEngine(
            config,
            broker=broker,
            market_data=MultiSymbolMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
            clock=lambda: datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
            trading_settings=settings,
            trading_session_state=TradingSessionState(),
            ai_provider=StaticAIProvider([ai_json()]),
        )

        result = engine.run_once()[0]

        self.assertIsNone(result["order"])
        self.assertEqual(result["response"]["reason"], "ai_direct_order_disabled")
        self.assertEqual(len(broker.orders), 0)

    def test_engine_fallback_to_rule_when_ai_fails(self):
        settings = TradingSettings(
            ai_ticker_selection_enabled=True,
            ai_trade_decision_enabled=True,
            ai_recommend_only=True,
            ai_candidate_tickers=["NVDA"],
            ai_fail_action="fallback_to_rule",
            ai_retry_count=0,
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
            ai_provider=StaticAIProvider(["not-json"]),
        )

        result = engine.run_once()[0]

        self.assertEqual(result["symbol"], "NVDA")
        self.assertNotIn("ai_decision", result)
        self.assertEqual(result["decision"].action, "buy")


if __name__ == "__main__":
    unittest.main()
