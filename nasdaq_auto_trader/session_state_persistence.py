from __future__ import annotations

from datetime import datetime, timezone

from .config_settings import TradingSessionState
from .trading_session_store import PersistedSafetyState, SessionStoreError, TradingSessionStore


def load_session_state(store: TradingSessionStore) -> TradingSessionState:
    persisted = store.load_safety_state()
    return TradingSessionState(
        market_date=persisted.market_date or None,
        buy_count=persisted.buy_count,
        sell_count=persisted.sell_count,
        daily_loss_breached=persisted.daily_loss_breached,
        daily_loss_state_unavailable=(
            persisted.baseline_observed and not persisted.daily_loss_breached
        ),
        last_order_at=_parse_timestamp(persisted.last_order_at),
    )


def save_session_state(
    store: TradingSessionStore,
    state: TradingSessionState,
) -> None:
    store.merge_safety_state(
        PersistedSafetyState(
            market_date=state.market_date or "",
            buy_count=state.buy_count,
            sell_count=state.sell_count,
            last_order_at=state.last_order_at.isoformat()
            if state.last_order_at is not None
            else "",
            daily_loss_breached=state.daily_loss_breached,
            baseline_observed=(
                state.starting_equity is not None
                or state.daily_loss_state_unavailable
            ),
        )
    )


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SessionStoreError("session_store_corrupt") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
