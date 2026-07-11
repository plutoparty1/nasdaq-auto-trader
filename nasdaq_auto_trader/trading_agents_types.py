from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict


TradingAgentsPolicy = Literal["advisory", "confirm", "replace"]
TradingAgentsStatus = Literal["ok", "unavailable", "error"]
TradingAgentsAction = Literal["buy", "sell", "hold"]


class TradingAgentsAnalysisResult(TypedDict, total=False):
    status: TradingAgentsStatus
    symbol: str
    analysis_date: str
    asset_type: str
    error: str
    install_command: str
    submitted_order: bool
    raw_decision: Any
    normalized_action: TradingAgentsAction
    selected_analysts: list[str]
    decision_policy: TradingAgentsPolicy
    final_state_keys: list[str]


@dataclass(frozen=True, slots=True)
class TradingAgentsConfig:
    enabled: bool = False
    decision_policy: TradingAgentsPolicy = "advisory"
    fail_closed: bool = True
    selected_analysts: list[str] = field(
        default_factory=lambda: ["market", "social", "news", "fundamentals"]
    )
    analysis_date: str | None = None
    asset_type: str = "stock"
    llm_provider: str | None = None
    deep_think_llm: str | None = None
    quick_think_llm: str | None = None
    backend_url: str | None = None
    output_language: str | None = None
    max_debate_rounds: int | None = 1
    max_risk_discuss_rounds: int | None = 1
    results_dir: str = "logs/tradingagents"
    data_cache_dir: str = "logs/tradingagents/cache"
    memory_log_path: str = "logs/tradingagents/memory/trading_memory.md"
    checkpoint_enabled: bool = False
    debug: bool = False
