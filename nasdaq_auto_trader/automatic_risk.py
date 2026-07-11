from __future__ import annotations

from dataclasses import dataclass, field, replace
import math

from .ai_quant_lab.artifact_paths import StrategyArtifactPaths
from .models import AccountSnapshot, OrderRequest, Position, TradeDecision
from .quant_data.symbol_selector import ResolvedStrategy
from .automatic_risk_config import (
    AutomaticRiskConfigBlock,
    load_automatic_risk_config,
)


@dataclass(frozen=True, slots=True)
class AutomaticRiskLimits:
    max_single_position_pct: float
    max_total_exposure_pct: float
    max_order_notional: float
    max_orders_per_day: int
    risk_per_trade_pct: float
    max_daily_loss_pct: float = 0.02


@dataclass(frozen=True, slots=True)
class AutomaticRiskBlock:
    reason: str


@dataclass(slots=True)  # noqa: MUTABLE_OK
class CycleReservationLedger:
    buy_notional: float = 0.0
    buy_notional_by_symbol: dict[str, float] = field(default_factory=dict)
    buy_qty_by_symbol: dict[str, float] = field(default_factory=dict)

    def adjusted_account(self, account: AccountSnapshot) -> AccountSnapshot:
        return AccountSnapshot(
            cash=max(account.cash - self.buy_notional, 0.0),
            equity=account.equity,
            buying_power=max(account.buying_power - self.buy_notional, 0.0),
        )

    def adjusted_position(
        self,
        symbol: str,
        position: Position | None,
    ) -> Position | None:
        reserved_qty = self.buy_qty_by_symbol.get(symbol, 0.0)
        reserved_value = self.buy_notional_by_symbol.get(symbol, 0.0)
        if reserved_qty <= 0 and reserved_value <= 0:
            return position
        return Position(
            symbol=symbol,
            qty=(position.qty if position is not None else 0.0) + reserved_qty,
            market_value=(
                position.market_value if position is not None else 0.0
            )
            + reserved_value,
            avg_entry_price=position.avg_entry_price if position is not None else 0.0,
        )

    def apply_limits(
        self,
        order: OrderRequest,
        decision: TradeDecision,
        latest_price: float,
        account: AccountSnapshot,
        positions: dict[str, Position],
        limits: AutomaticRiskLimits,
        submitted_order_count: int,
        starting_equity: float | None,
    ) -> tuple[OrderRequest, str]:
        if submitted_order_count >= limits.max_orders_per_day:
            return order, "learned_daily_order_limit_reached"
        if not _valid_order(order, latest_price):
            return order, "learned_order_notional_invalid"
        account_values = (account.cash, account.equity, account.buying_power)
        if any(not math.isfinite(value) or value < 0 for value in account_values):
            return order, "learned_exposure_state_unavailable"
        if any(
            not math.isfinite(position.qty)
            or not math.isfinite(position.market_value)
            or position.qty < 0
            or position.market_value < 0
            for position in positions.values()
        ):
            return order, "learned_exposure_state_unavailable"
        if order.side != "buy":
            return order, ""
        if (
            starting_equity is None
            or not math.isfinite(starting_equity)
            or starting_equity <= 0
        ):
            return order, "learned_daily_loss_state_unavailable"
        if account.equity <= starting_equity * (1 - limits.max_daily_loss_pct):
            return order, "learned_daily_loss_limit_reached"
        notional = order_notional(order, latest_price)
        if not math.isfinite(notional) or notional <= 0:
            return order, "learned_order_notional_invalid"
        if account.equity <= 0:
            return order, "learned_exposure_state_unavailable"
        market_values = tuple(position.market_value for position in positions.values())
        current_exposure = sum(max(value, 0.0) for value in market_values)
        total_available = max(
            account.equity * limits.max_total_exposure_pct
            - current_exposure
            - self.buy_notional,
            0.0,
        )
        current_symbol = positions.get(order.symbol)
        current_value = current_symbol.market_value if current_symbol is not None else 0.0
        single_available = max(
            account.equity * limits.max_single_position_pct
            - max(current_value, 0.0)
            - self.buy_notional_by_symbol.get(order.symbol, 0.0),
            0.0,
        )
        risk_available = math.inf
        if decision.risk_per_share is not None and decision.risk_per_share > 0:
            risk_available = (
                account.equity
                * limits.risk_per_trade_pct
                * latest_price
                / decision.risk_per_share
                if latest_price > 0
                else 0.0
            )
        caps = (
            (limits.max_order_notional, "learned_max_order_notional_reached"),
            (total_available, "learned_total_exposure_limit_reached"),
            (single_available, "learned_single_position_limit_reached"),
            (risk_available, "learned_risk_per_trade_limit_reached"),
        )
        allowed, reason = min(caps, key=lambda item: item[0])
        if notional <= allowed:
            return order, ""
        capped_notional = math.floor(allowed * 100) / 100
        if order.notional is not None and capped_notional >= 0.01:
            return replace(order, notional=capped_notional), ""
        return order, reason

    def reserve(
        self,
        order: OrderRequest,
        latest_price: float,
    ) -> None:
        if order.side != "buy":
            return
        notional = order_notional(order, latest_price)
        quantity = order.qty or (
            notional / latest_price if latest_price > 0 else 0.0
        )
        self.buy_notional += notional
        self.buy_notional_by_symbol[order.symbol] = (
            self.buy_notional_by_symbol.get(order.symbol, 0.0) + notional
        )
        self.buy_qty_by_symbol[order.symbol] = (
            self.buy_qty_by_symbol.get(order.symbol, 0.0) + quantity
        )


def resolve_automatic_risk_limits(
    paths: StrategyArtifactPaths,
    resolved: ResolvedStrategy,
) -> AutomaticRiskLimits | AutomaticRiskBlock:
    config = load_automatic_risk_config(paths.ai_config_path)
    if isinstance(config, AutomaticRiskConfigBlock):
        return AutomaticRiskBlock("ai_quant_config_invalid")
    controls = resolved.spec.risk_controls
    if not all(
        (
            controls.use_kill_switch,
            controls.block_if_data_stale,
            controls.block_if_spread_abnormal,
            controls.block_if_daily_loss_limit,
            controls.block_before_market_close,
            config.kill_switch_enabled,
            config.fail_closed,
        )
    ):
        return AutomaticRiskBlock("strategy_risk_controls_incomplete")
    sizing = resolved.spec.position_sizing
    return AutomaticRiskLimits(
        max_single_position_pct=min(
            config.max_single_position_pct,
            sizing.max_single_position_pct,
        ),
        max_total_exposure_pct=config.max_total_exposure_pct,
        max_order_notional=config.max_order_notional,
        max_orders_per_day=config.max_orders_per_day,
        risk_per_trade_pct=sizing.risk_per_trade_pct,
        max_daily_loss_pct=config.max_daily_loss_pct,
    )


def order_notional(order: OrderRequest, latest_price: float) -> float:
    if order.notional is not None:
        return max(order.notional, 0.0)
    return max((order.qty or 0.0) * latest_price, 0.0)


def _valid_order(order: OrderRequest, latest_price: float) -> bool:
    if order.side == "buy" and (
        not math.isfinite(latest_price) or latest_price <= 0
    ):
        return False
    quantity_valid = order.qty is None or (
        math.isfinite(order.qty) and order.qty > 0
    )
    notional_valid = order.notional is None or (
        math.isfinite(order.notional) and order.notional > 0
    )
    has_exactly_one_size = (order.qty is None) != (order.notional is None)
    return quantity_valid and notional_valid and has_exactly_one_size
