from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Protocol, TypeAlias

from .ai_quant_lab.audit_logger import AuditEvent
from .session_claims import SignalKey
from .quant_data.symbol_selector import ResolvedStrategy
from .models import OrderRequest


class AuditSink(Protocol):
    def append(self, event: AuditEvent) -> bool: ...


@dataclass(frozen=True, slots=True)
class AutomaticOrderContext:
    strategy_id: str
    strategy_version: str
    strategy_digest: str
    universe_id: str
    universe_effective_date: str
    risk_digest: str
    mode: str
    signal_timestamp: str
    max_daily_buy_count: int
    max_daily_sell_count: int
    cooldown_minutes: int
    daily_loss_breached: bool
    daily_loss_state_unavailable: bool
    baseline_available: bool
    universe_version: str = ""
    max_daily_order_count: int = 2**31 - 1
    learned_risk_digest: str = ""


@dataclass(frozen=True, slots=True)
class AutomaticOrderBlock:
    reason: str
    terminal: bool = False


@dataclass(frozen=True, slots=True)
class AutomaticOrderPermit:
    key: SignalKey
    context: AutomaticOrderContext
    started_monotonic: float


AutomaticOrderDecision: TypeAlias = AutomaticOrderPermit | AutomaticOrderBlock


@dataclass(frozen=True, slots=True)
class AutomaticBlockRequest:
    context: AutomaticOrderContext
    order: OrderRequest
    reason: str
    started_monotonic: float = field(default_factory=time.monotonic)
    terminal: bool = False


def strategy_mismatch(
    context: AutomaticOrderContext,
    resolved: ResolvedStrategy,
) -> str:
    if context.strategy_id != resolved.spec.strategy_id:
        return "promoted_strategy_id_changed"
    if context.strategy_version != resolved.spec.version:
        return "promoted_strategy_version_changed"
    if context.strategy_digest != resolved.spec_digest:
        return "promoted_strategy_digest_changed"
    return ""
