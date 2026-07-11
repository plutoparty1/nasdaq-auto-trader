from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditEvent, AuditLogger, NullAuditLogger
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig, live_order_block_reason
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.execution.kill_switch import KillSwitchResult


@dataclass(frozen=True, slots=True)
class OrderIntent:
    strategy_id: str
    symbol: str
    side: str
    order_qty: int
    current_price: float
    notional: float


@dataclass(frozen=True, slots=True)
class MarketHealth:
    data_stale: bool = False
    price_available: bool = True
    account_available: bool = True
    halted: bool = False
    tradable: bool = True
    spread_abnormal: bool = False
    volatility_abnormal: bool = False
    daily_loss_limit_reached: bool = False
    api_error_limit_reached: bool = False
    market_open_buffer_active: bool = False
    near_market_close: bool = False


@dataclass(frozen=True, slots=True)
class RiskGuardContext:
    config: AIQuantConfig
    intent: OrderIntent
    promoted_strategy: JsonObject | None
    market: MarketHealth = field(default_factory=MarketHealth)
    current_positions: dict[str, int] = field(default_factory=dict)
    available_cash: float = 0.0
    total_exposure: float = 0.0
    single_position_exposure: float = 0.0
    account_equity: float = 0.0
    symbol_position_value: float = 0.0
    kill_switch: KillSwitchResult | None = None


@dataclass(frozen=True, slots=True)
class RiskGuardResult:
    allowed: bool
    block_reason: str
    details: JsonObject
    checked_at: str


class RiskGuard:
    def __init__(self, audit_logger: AuditLogger | NullAuditLogger | None = None) -> None:
        self.audit_logger = audit_logger or NullAuditLogger()

    def check(self, context: RiskGuardContext) -> RiskGuardResult:
        reason = _durable_audit_block_reason(context, self.audit_logger) or _block_reason(context)
        allowed = reason == ""
        result = RiskGuardResult(
            allowed=allowed,
            block_reason=reason,
            details={"symbol": context.intent.symbol, "strategy_id": context.intent.strategy_id},
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
        audit_ok = self.audit_logger.append(
            AuditEvent(
                "risk_guard_checked",
                severity="info" if allowed else "warning",
                strategy_id=context.intent.strategy_id,
                payload={"allowed": allowed, "block_reason": reason},
            )
        )
        if not audit_ok:
            return RiskGuardResult(
                False,
                "audit_log_write_failed",
                result.details,
                result.checked_at,
            )
        return result


def _block_reason(context: RiskGuardContext) -> str:
    config_reason = live_order_block_reason(context.config)
    if config_reason is not None:
        return config_reason
    if context.kill_switch is not None and context.kill_switch.active:
        return context.kill_switch.reasons[0] if context.kill_switch.reasons else "kill_switch_active"
    promoted = context.promoted_strategy
    if promoted is None:
        return "promoted_strategy_missing"
    if promoted.get("status") != "champion":
        return "promoted_strategy_not_champion"
    if promoted.get("allowed_for_live") is not True:
        return "promoted_strategy_not_allowed_for_live"
    if promoted.get("manual_approval") is not True:
        return "manual_approval_missing"
    basis = promoted.get("research_basis")
    if not isinstance(basis, dict) or basis.get("provider") != "insane_search":
        return "research_provider_not_insane_search"
    if not basis.get("source_ids"):
        return "research_sources_missing"
    if promoted.get("active_strategy_id") != context.intent.strategy_id:
        return "strategy_id_mismatch"
    return _market_or_order_block_reason(context)


def _durable_audit_block_reason(
    context: RiskGuardContext,
    audit_logger: AuditLogger | NullAuditLogger,
) -> str:
    if (
        context.config.live_trading
        and not context.config.dry_run
        and context.config.controlled_live_enabled
        and not _has_real_durable_audit_sink(audit_logger)
    ):
        return "audit_logger_not_durable"
    return ""


def _has_real_durable_audit_sink(audit_logger: AuditLogger | NullAuditLogger) -> bool:
    return isinstance(audit_logger, AuditLogger) and audit_logger.durable


def _market_or_order_block_reason(context: RiskGuardContext) -> str:
    market = context.market
    intent = context.intent
    if market.data_stale:
        return "stale_data"
    if not market.price_available or intent.current_price <= 0:
        return "current_price_missing"
    if not market.account_available:
        return "account_lookup_failed"
    if intent.order_qty < 1:
        return "order_qty_below_minimum"
    if intent.side != "sell" and intent.notional > context.available_cash:
        return "available_cash_exceeded"
    if intent.notional > context.config.max_order_notional:
        return "max_order_notional_exceeded"
    if context.account_equity <= 0:
        return "account_equity_missing"
    if _projected_total_exposure_pct(context) > context.config.max_total_exposure_pct:
        return "total_exposure_exceeded"
    if _projected_single_position_pct(context) > context.config.max_single_position_pct:
        return "single_position_exposure_exceeded"
    if intent.side == "sell" and intent.order_qty > context.current_positions.get(intent.symbol, 0):
        return "sell_qty_exceeds_position"
    if market.halted:
        return "halted"
    if not market.tradable:
        return "not_tradable"
    if market.spread_abnormal:
        return "spread_abnormal"
    if market.volatility_abnormal:
        return "volatility_abnormal"
    if market.daily_loss_limit_reached:
        return "daily_loss_limit_reached"
    if market.api_error_limit_reached:
        return "api_error_limit_reached"
    if market.market_open_buffer_active:
        return "market_open_buffer_active"
    if market.near_market_close:
        return "near_market_close"
    return ""


def _projected_total_exposure_pct(context: RiskGuardContext) -> float:
    if context.intent.side == "sell":
        projected = max(context.total_exposure - context.intent.notional, 0.0)
    else:
        projected = context.total_exposure + context.intent.notional
    return projected / context.account_equity


def _projected_single_position_pct(context: RiskGuardContext) -> float:
    current_value = context.symbol_position_value
    if current_value <= 0 and context.single_position_exposure > 0:
        current_value = context.single_position_exposure * context.account_equity
    if context.intent.side == "sell":
        projected = max(current_value - context.intent.notional, 0.0)
    else:
        projected = current_value + context.intent.notional
    return projected / context.account_equity
