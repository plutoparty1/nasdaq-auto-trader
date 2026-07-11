"""AI recommendation orchestration for candidate ticker and order sizing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .ai_decision_schema import (
    AIDecisionSchemaError,
    AITradeRecommendation,
    parse_ai_trade_recommendation,
)
from .ai_decision_types import (
    AIDecisionResultDict,
    TradingAgentsRecommendationUnavailableError,
)
from .ai_market_summary import market_summary
from .config_manager import TradingSettings
from .models import AccountSnapshot, Bar, Position
from .trading_agents import TradingAgentsAdvisor, TradingAgentsAnalysisResult


class AIRecommendationProvider(Protocol):
    """Provider that returns one raw JSON recommendation string."""

    def request_ai_recommendation(
        self,
        prompt: str,
        context: "AIDecisionContext",
    ) -> str:
        """Return the AI provider's raw JSON string."""


@dataclass(frozen=True, slots=True)
class AIDecisionContext:
    """Inputs used to ask an AI provider for one recommendation."""

    candidate_tickers: list[str]
    account: AccountSnapshot
    positions: dict[str, Position]
    bars_by_symbol: dict[str, list[Bar]]
    settings: TradingSettings
    now: datetime


@dataclass(frozen=True, slots=True)
class AIDecisionResult:
    """AI decision attempt with enough detail for logging and safety review."""

    status: str
    prompt: str
    candidate_tickers: list[str]
    raw_response: str | None = None
    recommendation: AITradeRecommendation | None = None
    error: str | None = None
    parse_success: bool = False
    attempts: int = 0

    def to_dict(self) -> AIDecisionResultDict:
        return {
            "status": self.status,
            "candidate_tickers": self.candidate_tickers,
            "raw_response": self.raw_response,
            "parse_success": self.parse_success,
            "recommendation": self.recommendation.to_dict()
            if self.recommendation is not None
            else None,
            "error": self.error,
            "attempts": self.attempts,
            "prompt": self.prompt,
        }


class AIDecisionManager:
    """Build prompts, call an AI provider, and parse the strict JSON response."""

    def __init__(self, provider: AIRecommendationProvider) -> None:
        self.provider = provider

    def recommend(
        self,
        context: AIDecisionContext,
    ) -> AIDecisionResult:
        candidates = normalize_candidate_tickers(context.candidate_tickers)
        prompt = build_ai_decision_prompt(context, candidates)
        if not candidates:
            return AIDecisionResult(
                status="error",
                prompt=prompt,
                candidate_tickers=[],
                error="AI candidate ticker list is empty",
            )

        max_attempts = max(1, int(context.settings.ai_retry_count) + 1)
        last_error = None
        last_response = None
        for attempt in range(1, max_attempts + 1):
            try:
                raw_response = self.provider.request_ai_recommendation(prompt, context)
                last_response = raw_response
                recommendation = parse_ai_trade_recommendation(raw_response, candidates)
                return AIDecisionResult(
                    status="ok",
                    prompt=prompt,
                    candidate_tickers=candidates,
                    raw_response=raw_response,
                    recommendation=recommendation,
                    parse_success=True,
                    attempts=attempt,
                )
            except (AIDecisionSchemaError, Exception) as exc:
                last_error = f"{type(exc).__name__}: {exc}"

        return AIDecisionResult(
            status="error",
            prompt=prompt,
            candidate_tickers=candidates,
            raw_response=last_response,
            error=last_error,
            parse_success=False,
            attempts=max_attempts,
        )


class TradingAgentsRecommendationProvider:
    """Use existing TradingAgents per-symbol analysis to create strict JSON output."""

    def __init__(
        self,
        advisor: TradingAgentsAdvisor,
        analysis_date: str,
        asset_type: str = "stock",
    ) -> None:
        self.advisor = advisor
        self.analysis_date = analysis_date
        self.asset_type = asset_type

    def request_ai_recommendation(
        self,
        prompt: str,
        context: AIDecisionContext,
    ) -> str:
        del prompt
        analyses: list[TradingAgentsAnalysisResult] = []
        for ticker in normalize_candidate_tickers(context.candidate_tickers):
            analyses.append(
                self.advisor.analyze(
                    ticker,
                    self.analysis_date,
                    asset_type=self.asset_type,
                )
            )

        ok_results = [item for item in analyses if item.get("status") == "ok"]
        if not ok_results:
            first_error = analyses[0].get("error") if analyses else "no candidates"
            raise TradingAgentsRecommendationUnavailableError(
                f"TradingAgents recommendation unavailable: {first_error}"
            )

        selected = _select_tradingagents_result(ok_results, context.positions)
        action = selected.get("normalized_action", "hold")
        ticker = str(selected.get("symbol", context.candidate_tickers[0])).upper()
        order_qty = min(context.settings.order_qty, context.settings.ai_max_order_qty)
        confidence = 0.78 if action in ("buy", "sell") else 0.55
        return json.dumps(
            {
                "action": action,
                "ticker": ticker,
                "order_qty": max(int(order_qty), 1),
                "confidence": confidence,
                "reason": f"TradingAgents analysis returned {action} for {ticker}.",
                "risk": "AI output is advisory and still requires local risk guards.",
            },
            ensure_ascii=False,
        )


def normalize_candidate_tickers(values: list[str]) -> list[str]:
    """Return unique uppercase ticker symbols in user-provided order."""

    seen = set()
    result = []
    for value in values:
        ticker = str(value).strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        result.append(ticker)
    return result


def build_ai_decision_prompt(
    context: AIDecisionContext,
    candidates: list[str] | None = None,
) -> str:
    """Build the strict JSON-only AI prompt shown in logs for auditability."""

    settings = context.settings
    tickers = candidates or normalize_candidate_tickers(context.candidate_tickers)
    positions = {
        symbol: {
            "qty": position.qty,
            "market_value": position.market_value,
            "avg_entry_price": position.avg_entry_price,
        }
        for symbol, position in sorted(context.positions.items())
    }
    market_data = {
        ticker: market_summary(context.bars_by_symbol.get(ticker, []), settings)
        for ticker in tickers
    }
    return (
        "너는 나스닥 단기매매 보조 판단 엔진이다.\n\n"
        "아래 후보 종목 중에서만 판단해야 한다.\n"
        f"후보 종목: {json.dumps(tickers, ensure_ascii=False)}\n\n"
        "현재 계좌 상태:\n"
        f"- 사용 가능 현금: {context.account.buying_power}\n"
        f"- 현재 보유 종목 및 수량: {json.dumps(positions, ensure_ascii=False)}\n"
        f"- 최대 보유 수량: {settings.max_position_qty}\n"
        f"- AI 최대 주문 수량: {settings.ai_max_order_qty}\n"
        f"- 추가 매수 허용 여부: {settings.allow_additional_buy}\n"
        f"- 매도 전용 모드: {settings.sell_only}\n\n"
        f"시장 데이터: {json.dumps(market_data, ensure_ascii=False)}\n\n"
        "리스크 설정:\n"
        f"- 익절률: {settings.take_profit_rate}\n"
        f"- 손절률: {settings.stop_loss_rate}\n"
        f"- 트레일링 스탑 사용 여부: {settings.trailing_stop_enabled}\n"
        f"- 트레일링 스탑률: {settings.trailing_stop_rate}\n"
        f"- 일일 최대 손실률: {settings.max_daily_loss_rate}\n"
        f"- 장 마감 전 신규 매수 금지 시간: {settings.market_close_stop_minutes}\n\n"
        "반드시 아래 JSON 형식만 반환해라. 설명 문장, 마크다운, 코드블록은 절대 쓰지 마라.\n\n"
        "{\n"
        '  "action": "buy | sell | hold | skip",\n'
        '  "ticker": "후보 목록 중 하나",\n'
        '  "order_qty": 1,\n'
        '  "confidence": 0.0,\n'
        '  "reason": "판단 이유",\n'
        '  "risk": "위험 요소"\n'
        "}\n\n"
        "규칙:\n"
        "- 후보 목록 밖의 종목은 절대 선택하지 마라.\n"
        "- 확신이 낮으면 skip을 선택해라.\n"
        "- 주문 수량은 1 이상의 정수여야 한다.\n"
        "- 매수할 이유가 부족하면 hold 또는 skip을 선택해라.\n"
        "- 매도할 보유 수량이 없으면 sell을 선택하지 마라.\n"
    )

def _select_tradingagents_result(
    results: list[TradingAgentsAnalysisResult],
    positions: dict[str, Position],
) -> TradingAgentsAnalysisResult:
    for action in ("sell", "buy", "hold"):
        for result in results:
            if result.get("normalized_action") != action:
                continue
            if action == "sell" and positions.get(str(result.get("symbol", "")).upper()) is None:
                continue
            return result
    return results[0]
