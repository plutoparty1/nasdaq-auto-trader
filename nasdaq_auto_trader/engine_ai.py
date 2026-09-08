from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from .ai_decision_manager import (
    AIDecisionContext,
    AIDecisionManager,
    AIRecommendationProvider,
    TradingAgentsRecommendationProvider,
    normalize_candidate_tickers,
)
from .ai_decision_schema import AITradeRecommendation
from .ai_trade_guard import guard_ai_recommendation
from .config_manager import TradingSettings, record_submitted_order
from .engine_types import EngineCycleItem, JsonObject
from .models import AccountSnapshot, Bar, Position, TradeDecision


class EngineAIMixin:
    def _run_ai_decision_cycle(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        account: AccountSnapshot,
        positions: dict[str, Position],
    ) -> EngineCycleItem | None:
        """Run one AI recommendation cycle or return None for rule fallback."""

        settings = self.trading_settings
        if settings is None:
            return None

        now = self._clock()
        self.trading_session_state.reset_if_new_day(now)
        interval_block = self._ai_interval_block(settings, now)
        if interval_block is not None:
            return self._ai_blocked_item(
                "AI",
                interval_block,
                {
                    "status": "blocked",
                    "error": interval_block,
                    "candidate_tickers": self._ai_candidate_tickers(),
                },
            )

        for symbol in self._ai_candidate_tickers():
            self.trading_session_state.observe_position(symbol, positions.get(symbol), now)
        self.trading_session_state.observe_account(account, now)
        self.trading_session_state.last_ai_decision_at = now

        provider = self.ai_provider or self._default_ai_provider()
        manager = AIDecisionManager(provider)
        decision_result = manager.recommend(
            AIDecisionContext(
                candidate_tickers=self._ai_candidate_tickers(),
                account=account,
                positions=positions,
                bars_by_symbol=bars_by_symbol,
                settings=settings,
                now=now,
            )
        )
        ai_log: JsonObject = dict(decision_result.to_dict())
        if decision_result.status != "ok" or decision_result.recommendation is None:
            ai_log["final_status"] = "fallback_to_rule" if settings.ai_fail_action == "fallback_to_rule" else "blocked"
            if settings.ai_fail_action == "fallback_to_rule":
                return None
            failure_reason = (
                decision_result.error_code or "ai_recommendation_failed"
            )
            return self._ai_blocked_item("AI", failure_reason, ai_log)

        recommendation = decision_result.recommendation
        # Rule overlays must not turn this uncalibrated advisory provider into an order source.
        if not isinstance(provider, TradingAgentsRecommendationProvider):
            recommendation = self._effective_ai_recommendation(
                recommendation,
                bars_by_symbol,
                positions,
            )
        symbol = recommendation.ticker
        bars = bars_by_symbol.get(symbol, [])
        latest_price = bars[-1].close if bars else 0.0
        position = positions.get(symbol)
        order_account, buying_power_check = self._account_for_order(
            account,
            symbol,
            latest_price,
        )
        guard = guard_ai_recommendation(
            recommendation,
            settings,
            order_account,
            position,
            self.trading_session_state,
            now,
            self.config.mode,
            latest_price,
        )

        response = guard.response
        order = guard.order
        if order is not None and response is None:
            response = self._submit_or_block_order(order)
            record_submitted_order(order, response, self.trading_session_state, now)

        ai_log["recommendation"] = recommendation.to_dict()
        ai_log["validation_passed"] = order is not None and not (
            isinstance(response, dict) and response.get("status") == "blocked"
        )
        ai_log["order_submitted"] = bool(
            order is not None
            and isinstance(response, dict)
            and response.get("status") != "blocked"
        )
        if isinstance(response, dict) and response.get("status") == "blocked":
            ai_log["block_reason"] = response.get("reason")
            ai_log["final_status"] = f"blocked:{response.get('reason')}"
        elif order is None:
            ai_log["final_status"] = "no_order"
        else:
            ai_log["final_status"] = "order_attempted"

        decision_action = recommendation.action if recommendation.action in ("buy", "sell") else "hold"
        decision = TradeDecision(
            symbol,
            decision_action,
            int(recommendation.confidence * 100),
            latest_price,
            [
                "ai_recommendation",
                f"reason={recommendation.reason}",
                f"risk={recommendation.risk}",
            ],
        )
        return {
            "symbol": symbol,
            "decision": decision,
            "order": order,
            "response": response,
            "account": order_account,
            "buying_power_check": buying_power_check,
            "trading_agents": None,
            "ai_decision": ai_log,
        }

    def _trading_agents_advice(self, symbol: str) -> JsonObject | None:
        """Run optional TradingAgents analysis for a symbol."""

        if not self.config.trading_agents.enabled:
            return None
        analysis_date = (
            self.config.trading_agents.analysis_date
            or self._clock().date().isoformat()
        )
        return self.trading_agents.analyze(
            symbol,
            analysis_date,
            asset_type=self.config.trading_agents.asset_type,
        )

    def _ai_candidate_tickers(self) -> list[str]:
        settings = self.trading_settings
        if settings is None:
            return self.config.symbols
        if settings.ai_ticker_selection_enabled:
            return normalize_candidate_tickers(settings.ai_candidate_tickers)
        return normalize_candidate_tickers([settings.ticker])

    def _default_ai_provider(self) -> AIRecommendationProvider:
        analysis_date = (
            self.config.trading_agents.analysis_date
            or self._clock().date().isoformat()
        )
        return TradingAgentsRecommendationProvider(
            self.trading_agents,
            analysis_date,
            asset_type=self.config.trading_agents.asset_type,
        )

    def _effective_ai_recommendation(
        self,
        recommendation: AITradeRecommendation,
        bars_by_symbol: dict[str, list[Bar]],
        positions: dict[str, Position],
    ) -> AITradeRecommendation:
        settings = self.trading_settings
        if settings is None:
            return recommendation

        symbol = (
            recommendation.ticker
            if settings.ai_ticker_selection_enabled
            else settings.ticker.strip().upper()
        )
        order_qty = recommendation.order_qty if settings.ai_order_qty_enabled else settings.order_qty
        action = recommendation.action
        if not settings.ai_trade_decision_enabled:
            rule_decision = self.strategy.decide(
                symbol,
                bars_by_symbol.get(symbol, []),
                positions.get(symbol),
            )
            action = rule_decision.action
        return replace(
            recommendation,
            action=action,
            ticker=symbol,
            order_qty=order_qty,
        )

    def _ai_interval_block(
        self,
        settings: TradingSettings,
        now: datetime,
    ) -> str | None:
        last_decision_at = self.trading_session_state.last_ai_decision_at
        if last_decision_at is None:
            return None
        allowed_at = last_decision_at + timedelta(minutes=settings.ai_decision_interval_minutes)
        if now < allowed_at:
            return "ai_decision_interval_active"
        return None

    def _ai_blocked_item(
        self,
        symbol: str,
        reason: str,
        ai_decision: JsonObject,
    ) -> EngineCycleItem:
        return {
            "symbol": symbol,
            "decision": TradeDecision(symbol, "hold", 0, 0, [reason]),
            "order": None,
            "response": {
                "status": "blocked",
                "reason": reason,
                "ai_guard": True,
            },
            "account": self._load_account(),
            "buying_power_check": None,
            "trading_agents": None,
            "ai_decision": ai_decision,
        }
