from dataclasses import replace
from math import isfinite

from .models import TradeDecision


def price_entry_decision(
    decision: TradeDecision, ask: float | None, stop_loss_pct: float,
) -> TradeDecision:
    if decision.action != "buy" or ask is None:
        return decision
    if not isfinite(ask) or ask <= 0:
        return replace(decision, action="hold", reasons=["entry_quote_unavailable"])
    return replace(
        decision, latest_price=ask,
        risk_per_share=max(decision.risk_per_share or 0, ask * stop_loss_pct),
    )
