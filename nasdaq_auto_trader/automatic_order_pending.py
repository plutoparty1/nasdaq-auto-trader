from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .automatic_buy_receipts import automatic_buy_receipt_block
from .automatic_order_types import AutomaticOrderBlock
from .automatic_risk import CycleReservationLedger, order_notional
from .brokers.common import BrokerRequestError
from .models import OrderRequest, TradeDecision
from .trading_session_store import SessionStoreError

if TYPE_CHECKING:
    from .engine import TradingEngine


class OpenOrderView(Protocol):
    @property
    def symbol(self) -> str: ...

    @property
    def side(self) -> str: ...


@runtime_checkable
class OpenOrderSource(Protocol):
    def list_open_orders(self) -> Sequence[OpenOrderView]: ...


@dataclass(frozen=True, slots=True)
class PendingOrderCheck:
    initial_position_qty: float


def automatic_pending_order_block(
    engine: TradingEngine,
    order: OrderRequest,
    latest_price: float,
    *,
    risk_per_share: float | None = None,
) -> AutomaticOrderBlock | PendingOrderCheck:
    if not isinstance(engine.broker, OpenOrderSource):
        return AutomaticOrderBlock("automatic_open_order_check_unavailable", terminal=True)
    try:
        pending = engine.broker.list_open_orders()
        if any(item.symbol == order.symbol for item in pending):
            return AutomaticOrderBlock("automatic_symbol_open_order_pending")
        if order.side == "buy" and any(item.side == "buy" for item in pending):
            return AutomaticOrderBlock("automatic_buy_open_order_pending")
        positions = engine._load_positions(refresh=True)
        receipt_block = automatic_buy_receipt_block(engine, order, positions)
        if receipt_block is not None:
            return receipt_block
        position = positions.get(order.symbol)
        if order.side == "sell":
            if (
                order.qty is None or not isfinite(order.qty) or order.qty <= 0
                or position is None or not isfinite(position.qty) or position.qty < order.qty
            ):
                return AutomaticOrderBlock("automatic_sell_position_changed")
            return PendingOrderCheck(position.qty)
        account = engine._load_account(refresh=True)
        price = order.limit_price if order.limit_price is not None else latest_price
        if not isfinite(price) or price <= 0:
            return AutomaticOrderBlock("automatic_order_price_unavailable", terminal=True)
        account, _ = engine._account_for_order(account, order.symbol, price)
        settings_block = engine._settings_block_response(order, account, position)
        if settings_block is not None:
            return AutomaticOrderBlock(str(settings_block["reason"]))
        decision = TradeDecision(order.symbol, order.side, 0, price, [], risk_per_share)
        allowed = engine.risk_manager.build_order(decision, account, position, price)
        notional = order_notional(order, price)
        if allowed is None or order_notional(allowed, price) < notional:
            return AutomaticOrderBlock("automatic_order_capacity_changed")
        settings = engine.trading_settings
        requested_qty = order.qty if order.qty is not None else notional / price
        held_qty = position.qty if position is not None else 0
        if (settings is not None and not settings.integer_quantity_enabled
                and held_qty + requested_qty > settings.max_position_qty):
            return AutomaticOrderBlock("max_position_qty_exceeded")
        limits = engine.automatic_risk_limits
        if limits is not None:
            safety = engine.automatic_order_guard.session_store.load_safety_state()
            capped, reason = CycleReservationLedger().apply_limits(
                order, decision, price, account, positions, limits,
                max(safety.buy_count + safety.sell_count - 1, 0),
                engine.trading_session_state.starting_equity,
                integer_quantity_enabled=engine.config.risk.integer_quantity_enabled,
                estimated_roundtrip_cost_pct=engine.config.risk.estimated_roundtrip_cost_pct,
                estimated_roundtrip_minimum_cost_usd=engine.config.risk.estimated_roundtrip_minimum_cost_usd,
                estimated_sell_tax_pct=engine.config.risk.estimated_sell_tax_pct,
            )
            if reason:
                return AutomaticOrderBlock(reason)
            if order_notional(capped, price) < notional:
                return AutomaticOrderBlock("automatic_order_capacity_changed")
    except (BrokerRequestError, OSError, SessionStoreError):
        return AutomaticOrderBlock("automatic_order_reconciliation_unavailable", terminal=True)
    return PendingOrderCheck(position.qty if position is not None else 0.0)
