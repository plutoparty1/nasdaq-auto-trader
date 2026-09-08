"""AI recommendation orchestration for candidate ticker and order sizing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .ai_decision_schema import (
    AIDecisionSchemaError,
    AITradeRecommendation,
)
from .ai_decision_types import (
    AIDecisionErrorCode,
    AIDecisionResultDict,
    TradingAgentsRecommendationUnavailableError,
)
from .ai_supervisor_adapter import (
    SupervisorAdapterRequest,
    parse_provider_recommendation,
)
from .ai_decision_prompt import build_ai_decision_prompt, normalize_candidate_tickers
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

        ...


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
    error_code: AIDecisionErrorCode | None = None
    parse_success: bool = False
    attempts: int = 0

    def to_dict(self) -> AIDecisionResultDict:
        result: AIDecisionResultDict = {
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
        if self.error_code is not None:
            result["error_code"] = self.error_code
        return result


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
                recommendation = parse_provider_recommendation(
                    raw_response,
                    SupervisorAdapterRequest(
                        tuple(candidates),
                        context.settings.order_qty,
                        context.settings.ai_max_order_qty,
                        context.now,
                    ),
                )
                return AIDecisionResult(
                    status="ok",
                    prompt=prompt,
                    candidate_tickers=candidates,
                    raw_response=raw_response,
                    recommendation=recommendation,
                    parse_success=True,
                    attempts=attempt,
                )
            except TradingAgentsRecommendationUnavailableError as exc:
                return AIDecisionResult(
                    status="error",
                    prompt=prompt,
                    candidate_tickers=candidates,
                    raw_response=last_response,
                    error=f"{type(exc).__name__}: {exc}",
                    error_code="ai_provider_unavailable",
                    parse_success=False,
                    attempts=attempt,
                )
            except AIDecisionSchemaError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            except Exception as exc:  # noqa: BROAD_EXCEPT_OK
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
    """Expose uncalibrated TradingAgents analysis as a non-executable hold."""

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
        return json.dumps(
            {
                "action": "hold",
                "ticker": ticker,
                "order_qty": max(int(order_qty), 1),
                "confidence": 0.0,
                "reason": (
                    f"TradingAgents reported {action} for {ticker}; "
                    "calibrated confidence unavailable. Advisory analysis only."
                ),
                "risk": "Uncalibrated analysis cannot authorize orders; confidence 0 is not a probability estimate.",
            },
            ensure_ascii=False,
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
