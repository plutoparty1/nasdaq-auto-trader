import unittest

from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import (
    TradingSessionState,
    TradingSettings,
    apply_settings_to_app_config,
)
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot
from tests.ai_decision_fixtures import (
    FakeBroker,
    MultiSymbolMarketData,
    StaticAIProvider,
    ai_json,
    compact_strategy,
)


class AIDecisionEngineTests(unittest.TestCase):
    def _settings(self) -> TradingSettings:
        return TradingSettings(
            ai_ticker_selection_enabled=True,
            ai_order_qty_enabled=True,
            ai_trade_decision_enabled=True,
            ai_recommend_only=True,
            ai_candidate_tickers=["NVDA"],
            max_position_qty=5,
            ai_retry_count=0,
        )

    def _engine(self, response: str, broker: FakeBroker | None = None) -> TradingEngine:
        settings = self._settings()
        config = apply_settings_to_app_config(
            AppConfig(mode="dry_run", strategy=compact_strategy()),
            settings,
        )
        return TradingEngine(
            config,
            broker=broker or FakeBroker(),
            market_data=MultiSymbolMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
            trading_settings=settings,
            trading_session_state=TradingSessionState(),
            ai_provider=StaticAIProvider([response]),
        )

    def test_engine_ai_recommend_only_never_submits_order(self):
        broker = FakeBroker()
        result = self._engine(ai_json(), broker).run_once()[0]

        self.assertEqual(result["ai_decision"]["recommendation"]["ticker"], "NVDA")
        self.assertIsNone(result["order"])
        self.assertEqual(result["response"]["reason"], "ai_recommend_only")
        self.assertEqual(broker.orders, [])

    def test_engine_rejects_ai_candidate_outside_user_list(self):
        result = self._engine(ai_json(ticker="AAPL")).run_once()[0]

        self.assertEqual(result["response"]["reason"], "ai_recommendation_failed")
        self.assertFalse(result["ai_decision"]["parse_success"])

    def test_engine_rejects_non_finite_ai_confidence_without_crashing(self):
        raw_response = (
            '{"action": "buy", "ticker": "NVDA", "order_qty": 1, '
            '"confidence": NaN, "reason": "r", "risk": "k"}'
        )

        result = self._engine(raw_response).run_once()[0]

        self.assertEqual(result["response"]["reason"], "ai_recommendation_failed")
        self.assertFalse(result["ai_decision"]["parse_success"])
        self.assertIn("non-finite JSON number", result["ai_decision"]["error"])


if __name__ == "__main__":
    unittest.main()
