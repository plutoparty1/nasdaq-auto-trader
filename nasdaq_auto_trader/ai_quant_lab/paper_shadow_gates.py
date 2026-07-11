from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, assert_never

from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig

PaperShadowMode = Literal["paper", "shadow"]


@dataclass(frozen=True, slots=True)
class StageReadiness:
    allowed: bool
    next_status: str
    reasons: tuple[str, ...]


def evaluate_stage_readiness(
    mode: PaperShadowMode,
    observed_days: int,
    result_status: str,
    config: AIQuantConfig,
) -> StageReadiness:
    required_days = _required_days(mode, config)
    reasons: list[str] = []
    if observed_days < required_days:
        reasons.append(_minimum_days_reason(mode))
    if result_status != "completed":
        reasons.append(f"{mode}_result_not_completed")
    return StageReadiness(not reasons, _next_status(mode), tuple(reasons))


def _required_days(mode: PaperShadowMode, config: AIQuantConfig) -> int:
    match mode:
        case "paper":
            return config.min_paper_trading_days
        case "shadow":
            return config.min_shadow_live_days
        case unreachable:
            assert_never(unreachable)


def _next_status(mode: PaperShadowMode) -> str:
    match mode:
        case "paper":
            return "paper_trading"
        case "shadow":
            return "shadow_live"
        case unreachable:
            assert_never(unreachable)


def _minimum_days_reason(mode: PaperShadowMode) -> str:
    match mode:
        case "paper":
            return "min_paper_trading_days_not_met"
        case "shadow":
            return "min_shadow_live_days_not_met"
        case unreachable:
            assert_never(unreachable)
