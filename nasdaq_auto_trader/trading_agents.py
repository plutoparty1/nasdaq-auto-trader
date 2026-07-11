"""Optional TradingAgents integration for LLM-assisted trading analysis."""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any, Callable, Final, assert_never

from .models import TradeDecision
from .trading_agents_types import (
    TradingAgentsAction,
    TradingAgentsAnalysisResult,
    TradingAgentsConfig,
)


class UnknownTradingAgentsPolicyError(ValueError): pass


INSTALL_COMMAND = "pip install git+https://github.com/TauricResearch/TradingAgents.git"
RATING_ACTIONS: Final[dict[str, TradingAgentsAction]] = {
    "buy": "buy", "strong buy": "buy", "overweight": "buy", "sell": "sell",
    "strong sell": "sell", "underweight": "sell", "hold": "hold", "neutral": "hold",
}
BUY_SIGNAL_RE: Final[re.Pattern[str]] = re.compile(r"\b(?:buy|overweight)\b", re.I)
SELL_SIGNAL_RE: Final[re.Pattern[str]] = re.compile(r"\b(?:sell|underweight)\b", re.I)
NEGATED_ACTION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:do\s+not|don't|dont|never|no|not|avoid|refrain\s+from|should\s+not|"
    r"must\s+not|cannot|can't|cant|without)\s+(?:\w+\s+){0,3}?"
    r"(?:buy|sell|overweight|underweight)\b|"
    r"\b(?:buy|sell|overweight|underweight)\b(?:\s+\w+){0,3}?\s+"
    r"(?:not\s+recommended|is\s+not\s+recommended|should\s+not|must\s+not)\b",
    re.I,
)
UNCERTAIN_ACTION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:maybe|may|might|could|consider|possible|uncertain|unclear|ambiguous|"
    r"conflicting|mixed|not\s+sure|cannot\s+determine|can't\s+determine|"
    r"cant\s+determine)\b",
    re.I,
)
ADVERSARIAL_INSTRUCTION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:ignore|disregard|override|bypass|circumvent|disable|deactivate|turn\s+off|shut\s+off)\b"
    r"(?:\W+\w+){0,8}?\W+"
    r"\b(?:buy|sell|overweight|underweight|instructions?|guidance|rules?|"
    r"analysis|safety)\b",
    re.I,
)
ADVERSARIAL_CONTROL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:ignore|disregard|override|bypass|circumvent|disable|deactivate|turn\s+off|shut\s+off)\b"
    r"(?:\W+\w+){0,8}?\W+"
    r"\b(?:risk|controls?|safety|guardrails?|limits?|policy|policies)\b",
    re.I,
)
RATING_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:^|[\r\n])\s*(?:\*\*)?rating(?:\*\*)?\s*:?\s*([A-Za-z ]+)",
    re.I,
)


class TradingAgentsAdvisor:
    """Run TradingAgents when its external package is installed."""

    def __init__(
        self,
        config: TradingAgentsConfig | None = None,
        graph_cls: Any | None = None,
        default_config: dict[str, Any] | None = None,
    ) -> None:
        self.config = config or TradingAgentsConfig()
        self._graph_cls = graph_cls
        self._default_config = default_config

    def analyze(
        self,
        symbol: str,
        analysis_date: str,
        asset_type: str | None = None,
    ) -> TradingAgentsAnalysisResult:
        """Return a JSON-safe TradingAgents analysis result."""

        try:
            graph_cls, default_config = self._load_package()
        except Exception as exc:  # noqa: BROAD_EXCEPT_OK
            return _unavailable_result(symbol, analysis_date, exc)

        runtime_config = self._runtime_config(default_config)
        try:
            graph = graph_cls(
                selected_analysts=tuple(self.config.selected_analysts),
                debug=self.config.debug,
                config=runtime_config,
            )
            final_state, raw_decision = graph.propagate(
                symbol,
                analysis_date,
                asset_type=asset_type or self.config.asset_type,
            )
        except Exception as exc:  # noqa: BROAD_EXCEPT_OK
            return {
                "status": "error",
                "symbol": symbol,
                "analysis_date": analysis_date,
                "asset_type": asset_type or self.config.asset_type,
                "error": f"{type(exc).__name__}: {exc}",
                "submitted_order": False,
            }

        normalized_action = normalize_trading_agents_action(raw_decision)
        return {
            "status": "ok",
            "symbol": symbol,
            "analysis_date": analysis_date,
            "asset_type": asset_type or self.config.asset_type,
            "raw_decision": raw_decision,
            "normalized_action": normalized_action,
            "selected_analysts": list(self.config.selected_analysts),
            "decision_policy": self.config.decision_policy,
            "submitted_order": False,
            "final_state_keys": sorted(final_state.keys()) if isinstance(final_state, dict) else [],
        }

    def _load_package(self) -> tuple[Any, dict[str, Any]]:
        if self._graph_cls is not None and self._default_config is not None:
            return self._graph_cls, self._default_config

        graph_module = importlib.import_module("tradingagents.graph.trading_graph")
        config_module = importlib.import_module("tradingagents.default_config")
        return graph_module.TradingAgentsGraph, config_module.DEFAULT_CONFIG

    def _runtime_config(self, default_config: dict[str, Any]) -> dict[str, Any]:
        runtime_config = dict(default_config)
        overlays = {
            "llm_provider": self.config.llm_provider,
            "deep_think_llm": self.config.deep_think_llm,
            "quick_think_llm": self.config.quick_think_llm,
            "backend_url": self.config.backend_url,
            "output_language": self.config.output_language,
            "max_debate_rounds": self.config.max_debate_rounds,
            "max_risk_discuss_rounds": self.config.max_risk_discuss_rounds,
            "checkpoint_enabled": self.config.checkpoint_enabled,
        }
        for key, value in overlays.items():
            if value is not None:
                runtime_config[key] = value

        runtime_config["results_dir"] = str(Path(self.config.results_dir))
        runtime_config["data_cache_dir"] = str(Path(self.config.data_cache_dir))
        runtime_config["memory_log_path"] = str(Path(self.config.memory_log_path))
        return runtime_config


def normalize_trading_agents_action(decision: Any) -> TradingAgentsAction:
    """Map TradingAgents' 5-tier rating to this project's action vocabulary."""

    if isinstance(decision, dict):
        decision = decision.get("raw", decision)
    text = str(decision or "").strip()
    rating_match = RATING_RE.search(text)
    if rating_match:
        rating_phrase = rating_match.group(1)
        if NEGATED_ACTION_RE.search(rating_phrase) or UNCERTAIN_ACTION_RE.search(rating_phrase):
            return "hold"
        rating_action = _normalize_action_phrase(rating_phrase)
        if _rating_followup_is_unsafe(text[rating_match.end() :], rating_action):
            return "hold"
        return rating_action

    if (
        NEGATED_ACTION_RE.search(text)
        or UNCERTAIN_ACTION_RE.search(text)
        or ADVERSARIAL_INSTRUCTION_RE.search(text)
        or ADVERSARIAL_CONTROL_RE.search(text)
    ):
        return "hold"

    return _normalize_action_phrase(text)


def _rating_followup_is_unsafe(
    followup_text: str,
    rating_action: TradingAgentsAction,
) -> bool:
    if (
        ADVERSARIAL_INSTRUCTION_RE.search(followup_text)
        or ADVERSARIAL_CONTROL_RE.search(followup_text)
    ):
        return True
    for negated_action_match in NEGATED_ACTION_RE.finditer(followup_text):
        negated_action = negated_action_match.group(0)
        match rating_action:
            case "buy":
                if BUY_SIGNAL_RE.search(negated_action):
                    return True
            case "sell":
                if SELL_SIGNAL_RE.search(negated_action):
                    return True
            case "hold":
                return False
            case unreachable:
                assert_never(unreachable)
    return False


def _normalize_action_phrase(text: str) -> TradingAgentsAction:
    phrase = " ".join(text.strip().lower().split())
    if phrase in RATING_ACTIONS:
        return RATING_ACTIONS[phrase]

    buy_signal = BUY_SIGNAL_RE.search(phrase)
    sell_signal = SELL_SIGNAL_RE.search(phrase)
    if buy_signal and not sell_signal:
        return "buy"
    if sell_signal and not buy_signal:
        return "sell"
    return "hold"


def apply_trading_agents_policy(
    decision: TradeDecision,
    advice: dict | None,
    config: TradingAgentsConfig,
) -> TradeDecision:
    """Apply the configured TradingAgents decision policy to a technical signal."""

    if not config.enabled or config.decision_policy == "advisory":
        return decision

    if not advice or advice.get("status") != "ok":
        if not config.fail_closed:
            return decision
        return TradeDecision(
            decision.symbol,
            "hold",
            decision.score,
            decision.latest_price,
            [*decision.reasons, "tradingagents_unavailable_fail_closed"],
            decision.risk_per_share,
        )

    ta_action = advice.get("normalized_action", "hold")
    if config.decision_policy == "confirm":
        if decision.action in ("buy", "sell") and ta_action != decision.action:
            return TradeDecision(
                decision.symbol,
                "hold",
                decision.score,
                decision.latest_price,
                [
                    *decision.reasons,
                    f"tradingagents_{ta_action}_did_not_confirm_{decision.action}",
                ],
                decision.risk_per_share,
            )
        return TradeDecision(
            decision.symbol,
            decision.action,
            decision.score,
            decision.latest_price,
            [*decision.reasons, f"tradingagents_confirmed_{ta_action}"],
            decision.risk_per_share,
        )

    if config.decision_policy == "replace":
        return TradeDecision(
            decision.symbol,
            ta_action,
            decision.score,
            decision.latest_price,
            [f"tradingagents_replaced_with_{ta_action}", *decision.reasons],
            decision.risk_per_share,
        )

    raise UnknownTradingAgentsPolicyError(
        f"unknown TradingAgents decision policy: {config.decision_policy}"
    )


def _unavailable_result(symbol: str, analysis_date: str, exc: Exception) -> TradingAgentsAnalysisResult:
    return {
        "status": "unavailable",
        "symbol": symbol,
        "analysis_date": analysis_date,
        "error": f"{type(exc).__name__}: {exc}",
        "install_command": INSTALL_COMMAND,
        "submitted_order": False,
    }
