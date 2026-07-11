import unittest
from datetime import datetime, timezone

from nasdaq_auto_trader.ai_decision_manager import (
    AIDecisionContext,
    AIDecisionManager,
    TradingAgentsRecommendationProvider,
)
from nasdaq_auto_trader.app_format import _summarize_trade_result
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import (
    TradingSessionState,
    TradingSettings,
    apply_settings_to_app_config,
)
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.settings_window_fields_advanced import SETTINGS_SECTIONS_ADVANCED
from nasdaq_auto_trader.trading_agents import TradingAgentsAdvisor
from nasdaq_auto_trader.trading_agents_types import TradingAgentsAnalysisResult
from tests.ai_decision_fixtures import FakeBroker, MultiSymbolMarketData, compact_strategy


class _UnavailableAdvisor(TradingAgentsAdvisor):
    def analyze(
        self,
        symbol: str,
        analysis_date: str,
        asset_type: str | None = None,
    ) -> TradingAgentsAnalysisResult:
        return {
            "status": "unavailable",
            "symbol": symbol,
            "analysis_date": analysis_date,
            "asset_type": asset_type or "stock",
            "error": "ModuleNotFoundError: tradingagents",
        }


class AIFailureGuidanceTests(unittest.TestCase):
    def test_provider_unavailable_has_typed_code_and_stops_retrying(self):
        settings = TradingSettings(ai_retry_count=3)
        provider = TradingAgentsRecommendationProvider(
            _UnavailableAdvisor(),
            analysis_date="2026-07-11",
        )
        result = AIDecisionManager(provider).recommend(
            AIDecisionContext(
                candidate_tickers=["QQQ"],
                account=AccountSnapshot(10_000, 10_000, 10_000),
                positions={},
                bars_by_symbol={},
                settings=settings,
                now=datetime(2026, 7, 11, 2, 34, tzinfo=timezone.utc),
            )
        )

        self.assertEqual(result.error_code, "ai_provider_unavailable")
        self.assertEqual(result.attempts, 1)

    def test_formatter_explains_how_to_use_learned_selection(self):
        summary = _summarize_trade_result(
            {
                "ai_decision": {
                    "status": "error",
                    "error_code": "ai_provider_unavailable",
                    "error": "ModuleNotFoundError: secret internal path",
                    "recommendation": None,
                    "final_status": "blocked",
                },
                "response": {
                    "status": "blocked",
                    "reason": "ai_provider_unavailable",
                },
            }
        )

        self.assertIn("외부 AI 추천 기능이 준비되지 않았습니다", summary)
        self.assertIn("먼저 적격 학습 전략을 준비한 뒤", summary)
        self.assertIn("과거 데이터 기반 종목 자동 선택", summary)
        self.assertNotIn("secret internal path", summary)

    def test_engine_uses_specific_block_reason_when_provider_is_unavailable(self):
        settings = TradingSettings(
            ai_ticker_selection_enabled=True,
            ai_order_qty_enabled=True,
            ai_trade_decision_enabled=True,
            ai_candidate_tickers=["QQQ"],
            ai_retry_count=3,
        )
        config = apply_settings_to_app_config(
            AppConfig(mode="dry_run", strategy=compact_strategy()),
            settings,
        )
        engine = TradingEngine(
            config,
            broker=FakeBroker(),
            market_data=MultiSymbolMarketData(),
            account=AccountSnapshot(10_000, 10_000, 10_000),
            positions={},
            trading_settings=settings,
            trading_session_state=TradingSessionState(),
        )
        engine.trading_agents = _UnavailableAdvisor()

        result = engine.run_once()[0]

        self.assertEqual(result["response"]["reason"], "ai_provider_unavailable")
        self.assertEqual(result["ai_decision"]["error_code"], "ai_provider_unavailable")

    def test_settings_label_identifies_ai_trading_supervisor(self):
        section_title = SETTINGS_SECTIONS_ADVANCED[1][0]

        self.assertIn("AI Trading Supervisor", section_title)
        self.assertIn("선택 기능", section_title)


if __name__ == "__main__":
    unittest.main()
