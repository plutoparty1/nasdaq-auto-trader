from __future__ import annotations

import json
from dataclasses import replace

from .config import AppConfig
from .config_manager import (
    TradingSettings,
    apply_settings_to_app_config,
    load_or_create_settings,
)


def automatic_runtime_config(
    config: AppConfig,
    settings_path: str,
    preserve_mode: bool = True,
) -> tuple[AppConfig, TradingSettings]:
    settings = load_or_create_settings(settings_path)
    if preserve_mode:
        settings = replace(
            settings,
            auto_symbol_selection_enabled=True,
            dry_run=config.mode == "dry_run",
            live_trading=config.mode == "live",
            require_confirm_before_buy=False,
            require_confirm_before_sell=False,
        )
    else:
        settings = replace(settings, auto_symbol_selection_enabled=True)
    runtime = apply_settings_to_app_config(config, settings)
    if preserve_mode:
        runtime = replace(
            runtime,
            mode=config.mode,
            allow_live_trading=config.allow_live_trading,
        )
    return runtime, settings


def automatic_live_block(
    config: AppConfig,
    confirmed: bool,
    auth_minutes: int | None = None,
    max_cycles: int | None = None,
    require_envelope: bool = False,
) -> str | None:
    if config.mode != "live":
        return None
    if not config.allow_live_trading:
        return "live_trading_disabled"
    if not confirmed:
        return "live_order_confirmation_required"
    if require_envelope and (auth_minutes is None or max_cycles is None):
        return "live_authorization_required"
    if auth_minutes is None and max_cycles is None:
        return None
    if auth_minutes is None or max_cycles is None:
        return "live_authorization_required"
    if not 1 <= auth_minutes <= 60:
        return "live_authorization_minutes_out_of_range"
    if not 1 <= max_cycles <= 12:
        return "live_authorization_cycles_out_of_range"
    return None


def print_automatic_block(reason: str) -> None:
    print(
        json.dumps(
            {"status": "blocked", "reason": reason, "submitted_order": False},
            ensure_ascii=False,
            indent=2,
        )
    )
