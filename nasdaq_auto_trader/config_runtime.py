from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .config import AppConfig
from .config_settings import TradingSessionState, TradingSettings
from .config_validation import _ai_features_enabled, _normalized_tickers
from .market_hours import EASTERN, regular_market_session
from .models import AccountSnapshot, OrderRequest, Position


def apply_settings_to_app_config(
    base_config: AppConfig,
    settings: TradingSettings,
) -> AppConfig:
    """Map GUI settings onto the existing AppConfig/StrategyConfig/RiskConfig flow."""

    if settings.dry_run:
        mode = "dry_run"
        allow_live_trading = False
    elif settings.live_trading:
        mode = "live"
        allow_live_trading = True
    else:
        mode = "paper"
        allow_live_trading = False

    strategy = replace(
        base_config.strategy,
        sma_fast=settings.short_ma_period,
        sma_slow=settings.long_ma_period,
        ema_fast=settings.short_ma_period,
        ema_slow=settings.long_ma_period,
        long_sma=settings.long_ma_period,
        rsi_oversold=settings.buy_rsi_threshold,
        rsi_overbought=settings.sell_rsi_threshold,
        stop_loss_pct=settings.stop_loss_rate / 100,
        take_profit_pct=settings.take_profit_rate / 100,
        buy_trigger_enabled=settings.buy_trigger_enabled,
        buy_drop_rate=settings.buy_drop_rate,
        buy_ma_enabled=settings.buy_ma_enabled,
        trailing_stop_enabled=settings.trailing_stop_enabled,
        trailing_stop_activation_pct=settings.trailing_stop_activation_rate / 100,
        trailing_stop_pct=settings.trailing_stop_rate / 100,
        time_based_sell_enabled=settings.time_based_sell_enabled,
        max_holding_minutes=settings.max_holding_minutes,
    )
    risk = replace(
        base_config.risk,
        order_qty=settings.order_qty,
        max_position_qty=settings.max_position_qty,
        allow_additional_buy=settings.allow_additional_buy,
        min_cash_to_buy=settings.min_cash_to_buy,
    )

    symbols = [] if settings.auto_symbol_selection_enabled else [settings.ticker.strip().upper()]
    if (
        not settings.auto_symbol_selection_enabled
        and _ai_features_enabled(settings)
        and settings.ai_candidate_tickers
    ):
        symbols = _normalized_tickers(settings.ai_candidate_tickers)

    return replace(
        base_config,
        mode=mode,
        symbols=symbols,
        allow_live_trading=allow_live_trading,
        strategy=strategy,
        risk=risk,
    )


def validate_order_against_settings(
    order: OrderRequest,
    account: AccountSnapshot,
    position: Position | None,
    settings: TradingSettings,
    session_state: TradingSessionState,
    now: datetime,
    mode: str,
) -> dict | None:
    """Return a blocked response when a runtime safety rule rejects an order."""

    session_state.observe_account(account, now)
    side = order.side
    position_qty = position.qty if position is not None else 0

    if side == "buy":
        reason = _buy_block_reason(account, position_qty, settings, session_state, now)
    else:
        reason = _sell_block_reason(settings, session_state)

    if reason is None and mode != "dry_run":
        if side == "buy" and settings.require_confirm_before_buy:
            reason = "buy_confirmation_required"
        elif side == "sell" and settings.require_confirm_before_sell:
            reason = "sell_confirmation_required"

    if reason is None:
        return None
    return {
        "status": "blocked",
        "reason": reason,
        "settings_guard": True,
        "side": side,
    }


def record_submitted_order(
    order: OrderRequest,
    response: dict | None,
    session_state: TradingSessionState,
    now: datetime,
) -> None:
    """Update session counters after a non-blocked order attempt."""

    if not isinstance(response, dict):
        return
    if (
        response.get("status") == "blocked"
        and response.get("broker_submitted") is not True
    ):
        return
    session_state.record_order(order.side, now)


def _buy_block_reason(
    account: AccountSnapshot,
    position_qty: float,
    settings: TradingSettings,
    session_state: TradingSessionState,
    now: datetime,
) -> str | None:
    if settings.sell_only:
        return "sell_only_mode"
    if position_qty > 0 and not settings.allow_additional_buy:
        return "additional_buy_disabled"
    if position_qty + settings.order_qty > settings.max_position_qty:
        return "max_position_qty_exceeded"
    if account.cash < settings.min_cash_to_buy:
        return "min_cash_to_buy_not_met"
    if (
        settings.max_daily_buy_count > 0
        and session_state.buy_count >= settings.max_daily_buy_count
    ):
        return "max_daily_buy_count_reached"
    daily_loss_reason = _daily_loss_block_reason(account, settings, session_state)
    if daily_loss_reason:
        return daily_loss_reason
    if _cooldown_active(settings, session_state, now):
        return "cooldown_active"
    market_reason = _market_time_buy_block(settings, now)
    if market_reason:
        return market_reason
    return None


def _sell_block_reason(
    settings: TradingSettings,
    session_state: TradingSessionState,
) -> str | None:
    if (
        settings.max_daily_sell_count > 0
        and session_state.sell_count >= settings.max_daily_sell_count
    ):
        return "max_daily_sell_count_reached"
    return None


def _daily_loss_block_reason(
    account: AccountSnapshot,
    settings: TradingSettings,
    session_state: TradingSessionState,
) -> str | None:
    if session_state.daily_loss_breached:
        return "max_daily_loss_reached"
    if session_state.daily_loss_state_unavailable:
        return "daily_loss_state_unavailable"
    if settings.max_daily_loss_rate <= 0 or session_state.starting_equity in (None, 0):
        return None
    loss_limit = session_state.starting_equity * (1 - settings.max_daily_loss_rate / 100)
    if account.equity > loss_limit:
        return None
    session_state.daily_loss_breached = True
    return "max_daily_loss_reached"


def _cooldown_active(
    settings: TradingSettings,
    session_state: TradingSessionState,
    now: datetime,
) -> bool:
    if not settings.cooldown_enabled or settings.cooldown_minutes <= 0:
        return False
    if session_state.last_order_at is None:
        return False
    return now < session_state.last_order_at + timedelta(minutes=settings.cooldown_minutes)


def _market_time_buy_block(settings: TradingSettings, now: datetime) -> str | None:
    session = regular_market_session(now)
    if not session.is_open:
        return None
    market_now = datetime.fromisoformat(session.market_time)
    opens_at = datetime.fromisoformat(session.opens_at)
    closes_at = datetime.fromisoformat(session.closes_at)

    if settings.market_open_wait_minutes > 0:
        if market_now < opens_at + timedelta(minutes=settings.market_open_wait_minutes):
            return "market_open_wait_active"
    if settings.market_close_stop_minutes > 0:
        if market_now >= closes_at - timedelta(minutes=settings.market_close_stop_minutes):
            return "market_close_stop_active"
    return None


def _market_date(now: datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(EASTERN).date().isoformat()
