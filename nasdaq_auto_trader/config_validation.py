from __future__ import annotations

from .config_settings import TradingSettings, ValidationResult


def validate_settings(settings: TradingSettings) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not settings.auto_symbol_selection_enabled and not settings.ticker.strip():
        errors.append("ticker must not be empty")
    if (
        not settings.auto_symbol_selection_enabled
        and not settings.ticker.replace(".", "").replace("-", "").isalnum()
    ):
        errors.append("ticker must contain only letters, numbers, dot, or hyphen")

    _require_int_at_least(errors, "order_qty", settings.order_qty, 1)
    _require_int_at_least(errors, "max_position_qty", settings.max_position_qty, 1)
    if settings.max_position_qty < settings.order_qty:
        errors.append("max_position_qty must be greater than or equal to order_qty")

    _require_float_at_least(errors, "min_cash_to_buy", settings.min_cash_to_buy, 0)
    _require_float_at_least(errors, "buy_drop_rate", settings.buy_drop_rate, 0)
    _require_rsi(errors, "buy_rsi_threshold", settings.buy_rsi_threshold)
    _require_int_at_least(errors, "short_ma_period", settings.short_ma_period, 1)
    _require_int_at_least(errors, "long_ma_period", settings.long_ma_period, 1)
    if settings.long_ma_period < settings.short_ma_period:
        errors.append("long_ma_period must be greater than or equal to short_ma_period")

    _require_float_at_least(errors, "take_profit_rate", settings.take_profit_rate, 0)
    _require_float_at_least(errors, "stop_loss_rate", settings.stop_loss_rate, 0)
    _require_float_at_least(errors, "trailing_stop_rate", settings.trailing_stop_rate, 0)
    _require_rsi(errors, "sell_rsi_threshold", settings.sell_rsi_threshold)
    _require_int_at_least(errors, "max_holding_minutes", settings.max_holding_minutes, 1)

    _require_int_at_least(errors, "max_daily_buy_count", settings.max_daily_buy_count, 1)
    _require_int_at_least(errors, "max_daily_sell_count", settings.max_daily_sell_count, 1)
    _require_float_at_least(errors, "max_daily_loss_rate", settings.max_daily_loss_rate, 0)
    _require_int_at_least(errors, "cooldown_minutes", settings.cooldown_minutes, 0)
    _require_int_at_least(
        errors,
        "market_open_wait_minutes",
        settings.market_open_wait_minutes,
        0,
    )
    _require_int_at_least(
        errors,
        "market_close_stop_minutes",
        settings.market_close_stop_minutes,
        0,
    )
    if settings.save_log and not settings.log_path.strip():
        errors.append("log_path must not be empty when save_log is true")

    _require_float_between(errors, "ai_min_confidence", settings.ai_min_confidence, 0, 1)
    _require_int_at_least(errors, "ai_max_order_qty", settings.ai_max_order_qty, 1)
    _require_int_at_least(
        errors,
        "ai_decision_interval_minutes",
        settings.ai_decision_interval_minutes,
        1,
    )
    _require_int_at_least(errors, "ai_retry_count", settings.ai_retry_count, 0)
    if settings.ai_fail_action not in ("skip_trade", "fallback_to_rule"):
        errors.append("ai_fail_action must be skip_trade or fallback_to_rule")
    ai_candidates = _normalized_tickers(settings.ai_candidate_tickers)
    if _ai_features_enabled(settings) and not ai_candidates:
        errors.append("ai_candidate_tickers must not be empty when an AI feature is enabled")
    for ticker in ai_candidates:
        if not ticker.replace(".", "").replace("-", "").isalnum():
            errors.append(f"ai_candidate_tickers contains an invalid ticker: {ticker}")
    if (
        settings.ai_order_qty_enabled
        and settings.ai_max_order_qty > settings.max_position_qty
    ):
        errors.append("ai_max_order_qty must be less than or equal to max_position_qty")

    if settings.live_trading and settings.dry_run:
        warnings.append("live_trading=true with dry_run=true: dry_run will take priority")
    if (
        settings.live_trading
        and not settings.require_confirm_before_buy
        and not settings.require_confirm_before_sell
    ):
        warnings.append(
            "live_trading=true with both confirmations disabled: orders can be sent without a final prompt"
        )
    if settings.sell_only and settings.allow_additional_buy:
        warnings.append("sell_only=true: buy settings, including additional buys, will be ignored")
    if _ai_features_enabled(settings) and settings.ai_recommend_only:
        warnings.append("AI features are enabled in recommendation-only mode: no AI order will be sent")
    if (
        _ai_features_enabled(settings)
        and not settings.ai_recommend_only
        and not settings.require_confirm_after_ai
        and settings.live_trading
    ):
        warnings.append(
            "legacy AI direct orders remain disabled: final order submission "
            "will block with ai_direct_order_disabled"
        )

    return ValidationResult(errors, warnings)


def _normalized_tickers(values: list[str]) -> list[str]:
    seen = set()
    tickers = []
    for value in values:
        ticker = str(value).strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)
    return tickers


def _ai_features_enabled(settings: TradingSettings) -> bool:
    return ai_features_enabled(settings)


def ai_features_enabled(settings: TradingSettings) -> bool:
    """Return whether any AI recommendation feature is enabled."""

    return (
        settings.ai_ticker_selection_enabled
        or settings.ai_order_qty_enabled
        or settings.ai_trade_decision_enabled
    )


def _require_int_at_least(
    errors: list[str],
    name: str,
    value: int,
    minimum: int,
) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        errors.append(f"{name} must be an integer >= {minimum}")


def _require_float_at_least(
    errors: list[str],
    name: str,
    value: float,
    minimum: float,
) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < minimum:
        errors.append(f"{name} must be a number >= {minimum}")


def _require_float_between(
    errors: list[str],
    name: str,
    value: float,
    minimum: float,
    maximum: float,
) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{name} must be a number between {minimum} and {maximum}")
    elif value < minimum or value > maximum:
        errors.append(f"{name} must be between {minimum} and {maximum}")


def _require_rsi(errors: list[str], name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{name} must be a number between 0 and 100")
    elif value < 0 or value > 100:
        errors.append(f"{name} must be between 0 and 100")
