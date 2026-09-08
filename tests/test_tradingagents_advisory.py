"""Uncalibrated analysis must never authorize an order."""

from datetime import datetime, timezone

import pytest

from nasdaq_auto_trader.ai_decision_manager import (
    AIDecisionContext,
    AIDecisionManager,
    TradingAgentsRecommendationProvider,
)
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings, apply_settings_to_app_config
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, Position
from nasdaq_auto_trader.trading_agents import TradingAgentsAdvisor
from nasdaq_auto_trader.trading_agents_types import (
    TradingAgentsAction,
    TradingAgentsAnalysisResult,
)
from tests.ai_decision_fixtures import FakeBroker, MultiSymbolMarketData, compact_strategy


class ActionOnlyAdvisor(TradingAgentsAdvisor):
    def __init__(self, action: TradingAgentsAction) -> None:
        super().__init__()
        self.action = action

    def analyze(
        self, symbol: str, analysis_date: str, asset_type: str | None = None,
    ) -> TradingAgentsAnalysisResult:
        return {
            "status": "ok",
            "symbol": symbol,
            "analysis_date": analysis_date,
            "asset_type": asset_type or "stock",
            "normalized_action": self.action,
        }


@pytest.mark.parametrize("action", ("buy", "sell", "hold"))
def test_action_only_analysis_returns_advisory_hold(action: TradingAgentsAction) -> None:
    # Given: a successful action with no calibrated confidence evidence.
    context = AIDecisionContext(
        candidate_tickers=["QQQ"],
        account=AccountSnapshot(10_000, 10_000, 10_000),
        positions={"QQQ": Position("QQQ", 1, 100, 100)},
        bars_by_symbol={},
        settings=TradingSettings(ai_min_confidence=0),
        now=datetime(2026, 7, 11, 2, 34, tzinfo=timezone.utc),
    )
    provider = TradingAgentsRecommendationProvider(ActionOnlyAdvisor(action), "2026-07-11")

    # When: the real manager parses the provider response.
    result = AIDecisionManager(provider).recommend(context)

    # Then: the observed action remains useful without manufacturing certainty.
    assert result.status == "ok"
    recommendation = result.recommendation
    assert recommendation is not None
    assert recommendation.action == "hold"
    assert recommendation.confidence == 0
    assert f"reported {action}" in recommendation.reason
    assert "calibrated confidence unavailable" in recommendation.reason
    assert "cannot authorize orders" in recommendation.risk


@pytest.mark.parametrize("trade_decision_enabled", (True, False))
def test_advisory_analysis_cannot_order_with_zero_threshold(trade_decision_enabled: bool) -> None:
    # Given: automatic selection and permissive confidence, including rule overlay mode.
    settings = TradingSettings(
        ai_ticker_selection_enabled=True,
        ai_order_qty_enabled=True,
        ai_trade_decision_enabled=trade_decision_enabled,
        ai_candidate_tickers=["QQQ"],
        ai_min_confidence=0,
        ai_fail_action="fallback_to_rule",
    )
    config = apply_settings_to_app_config(
        AppConfig(mode="dry_run", strategy=compact_strategy()), settings,
    )
    broker = FakeBroker()
    engine = TradingEngine(
        config,
        broker=broker,
        market_data=MultiSymbolMarketData(),
        account=AccountSnapshot(10_000, 10_000, 10_000),
        positions={},
        trading_settings=settings,
    )
    engine.trading_agents = ActionOnlyAdvisor("buy")

    # When: the real engine executes a complete local cycle.
    result = engine.run_once()[0]

    # Then: neither direct AI mode nor rule overlay creates an order.
    assert result["decision"].action == "hold"
    assert result["order"] is None
    assert broker.orders == []
    assert result["ai_decision"]["order_submitted"] is False
