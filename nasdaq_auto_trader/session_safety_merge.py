from __future__ import annotations

from dataclasses import replace

from .position_high_water import merge_position_state
from .session_safety_reservation import PersistedSafetyState
from .session_state_codec import parsed_market_date


def merge_persisted_safety_state(
    persisted: PersistedSafetyState,
    current: PersistedSafetyState,
) -> PersistedSafetyState:
    persisted_date = parsed_market_date(persisted.market_date)
    current_date = parsed_market_date(current.market_date)
    if persisted_date is not None and current_date is not None and current_date < persisted_date:
        return persisted
    position_high_water, closed_symbols, position_state_versions = merge_position_state(
        persisted,
        current,
    )
    if current_date is None:
        return replace(
            persisted,
            position_high_water=position_high_water,
            closed_position_symbols=closed_symbols,
            position_state_versions=position_state_versions,
        )
    if persisted_date != current_date:
        return replace(
            current,
            position_high_water=position_high_water,
            closed_position_symbols=closed_symbols,
            position_state_versions=position_state_versions,
        )
    return PersistedSafetyState(
        market_date=current.market_date,
        buy_count=max(persisted.buy_count, current.buy_count),
        sell_count=max(persisted.sell_count, current.sell_count),
        last_order_at=max(persisted.last_order_at, current.last_order_at),
        daily_loss_breached=(
            persisted.daily_loss_breached or current.daily_loss_breached
        ),
        baseline_observed=persisted.baseline_observed or current.baseline_observed,
        position_high_water=position_high_water,
        closed_position_symbols=closed_symbols,
        position_state_versions=position_state_versions,
    )
