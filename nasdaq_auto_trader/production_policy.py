from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .config import AppConfig
from .config_settings import TradingSettings
from .models import OrderRequest
from .production_authorization import ProductionOrderGate

_gate: ProductionOrderGate | None = None


class ProductionOrderRuntime(Protocol):
    config: AppConfig
    trading_settings: TradingSettings | None
    production_order_gate: ProductionOrderGate | None

def configure_production_gate(gate: ProductionOrderGate) -> None:
    global _gate
    _gate = gate


def production_order_block(
    runtime: ProductionOrderRuntime, order: OrderRequest, now: datetime,
) -> str:
    gate = runtime.production_order_gate
    if gate is None or runtime.config.mode != "live":
        return ""
    reason = gate.reason(runtime.config, runtime.trading_settings, now)
    return reason or gate.order_reason(order)
