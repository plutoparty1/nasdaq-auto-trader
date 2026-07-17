from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .market_hours import EASTERN
from .models import AccountSnapshot, Position


class SettingsError(RuntimeError):
    pass


class SettingsLoadError(SettingsError):
    pass


class SettingsValidationError(SettingsError):
    def __init__(self, errors: list[str], warnings: list[str] | None = None) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors
        self.warnings = warnings or []


class SettingsValueError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Validation messages separated by severity."""

    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class TradingSettings:
    """User-editable GUI settings stored in trading_config.json."""

    live_trading: bool = False
    dry_run: bool = True
    require_confirm_before_sell: bool = True
    require_confirm_before_buy: bool = True
    sell_only: bool = False
    allow_additional_buy: bool = False
    auto_symbol_selection_enabled: bool = False
    ticker: str = "QQQ"
    order_qty: int = 1
    max_position_qty: int = 1
    min_cash_to_buy: float = 0.0
    buy_trigger_enabled: bool = False
    buy_drop_rate: float = 0.0
    buy_rsi_threshold: float = 30.0
    buy_ma_enabled: bool = True
    short_ma_period: int = 5
    long_ma_period: int = 20
    take_profit_rate: float = 5.0
    stop_loss_rate: float = 3.0
    trailing_stop_enabled: bool = False
    trailing_stop_rate: float = 2.0
    sell_rsi_threshold: float = 70.0
    time_based_sell_enabled: bool = False
    max_holding_minutes: int = 180
    max_daily_buy_count: int = 1
    max_daily_sell_count: int = 1
    max_daily_loss_rate: float = 5.0
    cooldown_enabled: bool = False
    cooldown_minutes: int = 0
    market_open_wait_minutes: int = 0
    market_close_stop_minutes: int = 10
    telegram_enabled: bool = False
    discord_enabled: bool = False
    notify_order: bool = True
    notify_signal: bool = True
    notify_error: bool = True
    save_log: bool = True
    log_path: str = "logs/trader.log"
    stop_on_order_error: bool = True
    unattended_operation_enabled: bool = False
    unattended_live_trading_enabled: bool = False
    unattended_interval_minutes: int = 15
    daily_report_enabled: bool = True
    daily_report_hour: int = 8
    daily_report_minute: int = 0
    daily_report_retention_days: int = 90
    ai_ticker_selection_enabled: bool = False
    ai_order_qty_enabled: bool = False
    ai_trade_decision_enabled: bool = False
    ai_recommend_only: bool = True
    require_confirm_after_ai: bool = True
    ai_min_confidence: float = 0.7
    ai_max_order_qty: int = 1
    ai_candidate_tickers: list[str] = field(
        default_factory=lambda: ["AAPL", "MSFT", "NVDA", "TSLA", "QQQ"]
    )
    ai_decision_interval_minutes: int = 5
    ai_retry_count: int = 1
    ai_fail_action: str = "skip_trade"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)  # noqa: MUTABLE_OK
class TradingSessionState:
    """In-memory counters used for per-session runtime safety checks."""

    market_date: str | None = None
    buy_count: int = 0
    sell_count: int = 0
    starting_equity: float | None = None
    daily_loss_breached: bool = False
    daily_loss_state_unavailable: bool = False
    last_order_at: datetime | None = None
    last_ai_decision_at: datetime | None = None
    position_first_seen_at: dict[str, datetime] = field(default_factory=dict)

    def reset_if_new_day(self, now: datetime) -> None:
        market_date = _market_date(now)
        if self.market_date is None:
            self.market_date = market_date
            return
        if self.market_date == market_date:
            return
        self.market_date = market_date
        self.buy_count = 0
        self.sell_count = 0
        self.starting_equity = None
        self.daily_loss_breached = False
        self.daily_loss_state_unavailable = False
        self.last_order_at = None
        self.last_ai_decision_at = None

    def observe_account(self, account: AccountSnapshot, now: datetime) -> None:
        self.reset_if_new_day(now)
        if (
            self.starting_equity is None
            and not self.daily_loss_breached
            and not self.daily_loss_state_unavailable
            and account.equity > 0
        ):
            self.starting_equity = account.equity

    def record_order(self, side: str, now: datetime) -> None:
        self.reset_if_new_day(now)
        if side == "buy":
            self.buy_count += 1
        elif side == "sell":
            self.sell_count += 1
        self.last_order_at = now

    def observe_position(self, symbol: str, position: Position | None, now: datetime) -> None:
        if position is not None and position.qty > 0:
            self.position_first_seen_at.setdefault(symbol, now)
        else:
            self.position_first_seen_at.pop(symbol, None)

    def held_minutes(self, symbol: str, now: datetime) -> float | None:
        first_seen = self.position_first_seen_at.get(symbol)
        if first_seen is None:
            return None
        return max((now - first_seen).total_seconds() / 60, 0)


def _market_date(now: datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(EASTERN).date().isoformat()
