from __future__ import annotations

from .experimental_exit_models import ExitDiagnostics, ExitPolicy
from .experimental_exit_state import (
    ExitStateStore,
    initial_stop,
    retained_stop,
    valid_atr,
)
from .models import Bar, Position
from .strategy_config import StrategyConfig


def snapshot(policy: ExitPolicy, config: StrategyConfig, store: ExitStateStore, symbol: str,
             bars: list[Bar], position: Position | None) -> ExitDiagnostics:
    state = store.positions.get(symbol)
    volatility = valid_atr(bars, config.atr_period if policy.stop_mode == "legacy" else policy.atr_period)
    entry = None if position is None else position.avg_entry_price
    price = bars[-1].close
    source = "completed_bar_close"
    if position is not None and position.qty > 0 and position.market_value > 0:
        price = position.market_value / position.qty
        source = "position_market_value_div_qty"
    legacy = policy.stop_mode == "legacy"
    primary = None if state is None else state.initial_stop_price
    if legacy and entry is not None:
        primary = initial_stop(policy, config, entry, volatility)
    fixed_pct = config.stop_loss_pct if legacy else policy.fixed_stop_pct
    activation = config.trailing_stop_activation_pct if legacy else policy.trailing_activation_pct
    drawdown = config.trailing_stop_pct if legacy else policy.trailing_drawdown_pct
    active = state is not None and state.trailing_active
    if legacy and state is not None and entry is not None:
        active = config.trailing_stop_enabled and state.high_water_price >= entry * (1 + activation)
    effective = None if state is None else (primary if legacy else retained_stop(state))
    atr_stop = None
    if entry is not None and volatility is not None and legacy:
        atr_stop = entry - volatility * config.atr_stop_multiplier
    if state is not None and policy.stop_mode == "entry_atr":
        atr_stop = state.initial_stop_price
    return ExitDiagnostics(
        symbol=symbol, stop_mode=policy.stop_mode, profile_fingerprint=store.fingerprint,
        price=price, price_source=source,
        price_timestamp=bars[-1].timestamp if source == "completed_bar_close" else None,
        bar_timestamp=bars[-1].timestamp, bar_interval=policy.bar_interval, entry_price=entry,
        fixed_stop_price=None if entry is None else entry * (1 - fixed_pct),
        current_atr=volatility, entry_atr=None if state is None else state.entry_atr,
        atr_stop_price=atr_stop, initial_stop_price=None if state is None else state.initial_stop_price,
        effective_stop_price=effective,
        emergency_stop_price=None if state is None else state.emergency_stop_price,
        high_water_price=None if state is None else state.high_water_price, trailing_active=active,
        trailing_price=None if not active or state is None else state.high_water_price * (1 - drawdown),
    )
