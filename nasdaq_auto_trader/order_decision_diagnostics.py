from __future__ import annotations

from .ai_quant_lab.types import JsonObject
from .models import AccountSnapshot, Position, TradeDecision
from .risk import RiskConfig


def decision_risk_costs(
    decision: TradeDecision, account: AccountSnapshot,
    position: Position | None, risk: RiskConfig,
    *,
    planned_quantity: float | None = None,
) -> JsonObject:
    qty = float(risk.order_qty or 1) if planned_quantity is None else planned_quantity
    if position is not None and planned_quantity is None:
        qty = position.qty
    price = decision.latest_price
    cost = (max(price * qty * risk.estimated_roundtrip_cost_pct,
                risk.estimated_roundtrip_minimum_cost_usd)
            + price * qty * risk.estimated_sell_tax_pct) if qty > 0 else 0
    distance = decision.risk_per_share
    gross = (price - position.avg_entry_price) * qty if position else None
    return {
        "account_equity": account.equity,
        "risk_budget": account.equity * risk.risk_per_trade_pct,
        "risk_per_trade_pct": risk.risk_per_trade_pct,
        "planned_quantity": qty,
        "estimated_roundtrip_minimum_cost_usd": risk.estimated_roundtrip_minimum_cost_usd,
        "estimated_sell_tax_pct": risk.estimated_sell_tax_pct,
        "initial_risk_per_share": distance,
        "planned_loss_including_estimated_cost":
            distance * qty + cost if distance is not None else None,
        "estimated_roundtrip_cost": cost,
        "estimated_roundtrip_cost_pct": risk.estimated_roundtrip_cost_pct,
        "cost_source": risk.estimated_cost_source,
        "expected_gross_profit": gross,
        "expected_profit_after_estimated_cost": gross - cost if gross is not None else None,
        "actual_fees": None,
        "exit_allowed_independently_of_expected_profit": True,
    }
