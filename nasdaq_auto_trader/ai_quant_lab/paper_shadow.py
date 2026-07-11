from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditEvent, NullAuditLogger
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.paper_shadow_gates import (
    PaperShadowMode,
    StageReadiness,
    evaluate_stage_readiness,
)
from nasdaq_auto_trader.ai_quant_lab.paper_shadow_ledger import PaperShadowLedger
from nasdaq_auto_trader.ai_quant_lab.post_trade_feedback import (
    ActualExecution,
    ExpectedExecution,
    PostTradeFeedback,
    analyze_post_trade_feedback,
)
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.execution.position_sizer import (
    PortfolioState,
    PositionSizer,
    SizingRequest,
)
from nasdaq_auto_trader.strategies.base_strategy import TargetPosition

__all__ = [
    "ActualExecution",
    "ExpectedExecution",
    "PaperShadowEngine",
    "PaperShadowLedger",
    "PaperShadowMode",
    "PaperShadowRequest",
    "PaperShadowResult",
    "PostTradeFeedback",
    "StageReadiness",
    "VirtualFill",
    "analyze_post_trade_feedback",
    "evaluate_stage_readiness",
]


@dataclass(frozen=True, slots=True)
class VirtualFill:
    strategy_id: str
    symbol: str
    side: str
    qty: int
    signal_price: float
    fill_price: float
    notional: float
    cost: float
    as_of: str

    def to_json_object(self) -> JsonObject:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "signal_price": self.signal_price,
            "fill_price": self.fill_price,
            "notional": self.notional,
            "cost": self.cost,
            "as_of": self.as_of,
        }


@dataclass(frozen=True, slots=True)
class PaperShadowRequest:
    strategy_id: str
    strategy_version: str
    mode: PaperShadowMode
    targets: tuple[TargetPosition, ...]
    portfolio: PortfolioState
    market_prices: dict[str, float]
    as_of: str
    champion_return: float = 0.0


@dataclass(frozen=True, slots=True)
class PaperShadowResult:
    strategy_id: str
    strategy_version: str
    mode: PaperShadowMode
    status: str
    fills: tuple[VirtualFill, ...]
    equity_curve: tuple[float, ...]
    net_pnl: float
    champion_delta: float
    blocked_reasons: tuple[str, ...]
    submitted_orders: int = 0

    def to_json_object(self) -> JsonObject:
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "mode": self.mode,
            "status": self.status,
            "fills": [fill.to_json_object() for fill in self.fills],
            "equity_curve": list(self.equity_curve),
            "net_pnl": self.net_pnl,
            "champion_delta": self.champion_delta,
            "blocked_reasons": list(self.blocked_reasons),
            "submitted_orders": self.submitted_orders,
        }


class PaperShadowEngine:
    def __init__(
        self,
        config: AIQuantConfig | None = None,
        audit_logger: NullAuditLogger | None = None,
    ) -> None:
        self.config = config or AIQuantConfig()
        self.audit_logger = audit_logger or NullAuditLogger()
        self.position_sizer = PositionSizer(self.config)

    def run(self, request: PaperShadowRequest) -> PaperShadowResult:
        fills: list[VirtualFill] = []
        blocked: list[str] = []
        equity = request.portfolio.account_equity
        for target in request.targets:
            if target.side not in ("buy", "sell"):
                blocked.append("unsupported_side")
                continue
            price = request.market_prices.get(target.symbol, target.entry_price)
            sizing = self.position_sizer.calculate(
                SizingRequest(target, request.portfolio, price)
            )
            if sizing.blocked_reason:
                blocked.append(sizing.blocked_reason)
                continue
            fills.append(
                _virtual_fill(target, sizing.order_qty, price, request.as_of, self.config)
            )
        net_pnl = _net_pnl(fills)
        result = PaperShadowResult(
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            mode=request.mode,
            status="completed" if not blocked else "blocked",
            fills=tuple(fills),
            equity_curve=(equity, equity + net_pnl),
            net_pnl=net_pnl,
            champion_delta=net_pnl - request.champion_return,
            blocked_reasons=tuple(blocked),
        )
        if not self.audit_logger.append(
            AuditEvent(
                _signal_event_type(request.mode),
                strategy_id=request.strategy_id,
                strategy_version=request.strategy_version,
                payload={
                    "fills": len(fills),
                    "blocked": list(blocked),
                    "net_pnl": net_pnl,
                },
            )
        ):
            return PaperShadowResult(
                request.strategy_id,
                request.strategy_version,
                request.mode,
                "blocked",
                (),
                (equity,),
                0.0,
                -request.champion_return,
                ("audit_log_write_failed",),
            )
        return result


def _virtual_fill(
    target: TargetPosition,
    qty: int,
    signal_price: float,
    as_of: str,
    config: AIQuantConfig,
) -> VirtualFill:
    cost_bps = config.slippage_bps + config.commission_bps
    multiplier = (
        1 + cost_bps / 10_000
        if target.side == "buy"
        else 1 - cost_bps / 10_000
    )
    fill_price = signal_price * multiplier
    return VirtualFill(
        target.strategy_id,
        target.symbol,
        target.side,
        qty,
        signal_price,
        fill_price,
        qty * fill_price,
        abs(qty * signal_price * cost_bps / 10_000),
        as_of,
    )


def _net_pnl(fills: list[VirtualFill]) -> float:
    return -sum(fill.cost for fill in fills)


def _signal_event_type(mode: PaperShadowMode) -> str:
    match mode:
        case "paper":
            return "paper_signal_generated"
        case "shadow":
            return "shadow_signal_generated"
        case unreachable:
            assert_never(unreachable)
