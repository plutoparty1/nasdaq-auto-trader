from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KillSwitchState:
    daily_loss_limit_reached: bool = False
    strategy_drawdown_exceeded: bool = False
    consecutive_order_failures: int = 0
    consecutive_api_errors: int = 0
    stale_data: bool = False
    price_outlier: bool = False
    audit_log_failed: bool = False
    manual_kill_switch: bool = False
    promoted_strategy_corrupt: bool = False
    research_basis_missing: bool = False


@dataclass(frozen=True, slots=True)
class KillSwitchResult:
    active: bool
    reasons: tuple[str, ...]


class KillSwitch:
    def evaluate(self, state: KillSwitchState) -> KillSwitchResult:
        reasons: list[str] = []
        if state.daily_loss_limit_reached:
            reasons.append("daily_loss_limit_reached")
        if state.strategy_drawdown_exceeded:
            reasons.append("strategy_drawdown_exceeded")
        if state.consecutive_order_failures >= 3:
            reasons.append("consecutive_order_failures")
        if state.consecutive_api_errors >= 3:
            reasons.append("consecutive_api_errors")
        if state.stale_data:
            reasons.append("stale_data")
        if state.price_outlier:
            reasons.append("price_outlier")
        if state.audit_log_failed:
            reasons.append("audit_log_failed")
        if state.manual_kill_switch:
            reasons.append("manual_kill_switch")
        if state.promoted_strategy_corrupt:
            reasons.append("promoted_strategy_corrupt")
        if state.research_basis_missing:
            reasons.append("research_basis_missing")
        return KillSwitchResult(bool(reasons), tuple(reasons))
