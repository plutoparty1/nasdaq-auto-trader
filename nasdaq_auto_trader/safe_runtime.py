"""Irreversible process policy for the separately packaged simulation release."""
from __future__ import annotations

from dataclasses import replace
from threading import Event
from typing import Final

from .config import AppConfig
from .config_settings import TradingSettings

BUILD_ID: Final = "roundtrip-repair-20261013-r2"
_ORDER_LOCK: Final = Event()


def enable() -> None:
    """Latch the process order lock; this module exposes no unlock operation."""
    _ORDER_LOCK.set()


def orders_locked() -> bool:
    """Return whether all broker submission is forbidden in this process."""
    return _ORDER_LOCK.is_set()


def sanitize_config(config: AppConfig) -> AppConfig:
    """Remove credentials and live authority irrespective of saved GUI values."""
    return replace(
        config, mode="dry_run", allow_live_trading=False,
        live_environment_authorized=False,
        trading_agents=replace(config.trading_agents, enabled=False),
        alpaca=replace(config.alpaca, api_key="", secret_key="", paper=True),
        kis=replace(config.kis, app_key="", app_secret="", account_no="", paper=True),
    )


def sanitize_settings(settings: TradingSettings) -> TradingSettings:
    """Apply the visible release policy after every user-settings load."""
    return replace(
        settings, dry_run=True, live_trading=False,
        daily_minimum_buy_enabled=False, daily_forced_order_enabled=False,
        automatic_session_authorization_enabled=False,
        unattended_live_trading_enabled=False,
        telegram_enabled=False, discord_enabled=False,
    )
