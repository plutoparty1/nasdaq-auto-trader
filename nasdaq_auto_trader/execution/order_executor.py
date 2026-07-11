from __future__ import annotations

from typing import Protocol

from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.execution.risk_guard import OrderIntent, RiskGuardResult


class BrokerOrderClient(Protocol):
    def submit_order(self, intent: OrderIntent) -> JsonObject: ...


class OrderExecutor:
    def submit_after_risk_guard(
        self,
        broker: BrokerOrderClient,
        intent: OrderIntent,
        guard: RiskGuardResult,
    ) -> JsonObject:
        if not guard.allowed:
            return {"status": "blocked", "reason": guard.block_reason}
        return broker.submit_order(intent)
