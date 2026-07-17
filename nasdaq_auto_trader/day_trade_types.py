from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .models import AccountSnapshot, OrderRequest


TAKE_PROFIT_PCT = 1.5
STOP_LOSS_PCT = -1.0
MAX_HOLD_MINUTES = 180
MAX_TOTAL_USD = 64.0
FEE_BUFFER_USD = 0.50
FEE_BUFFER_PCT = 0.25
FORCE_EXIT_MINUTES_BEFORE_CLOSE = 15
CONFIRMATION_PRICE_TOLERANCE_PCT = 1.0

JsonObject = dict[str, Any]
BrokerResponse = dict[str, Any]
DayTradePlan = dict[str, Any]
DayTradeSubmissionResult = dict[str, Any]
LiveBuyConfirmation = dict[str, Any]
LiveBuyPreview = dict[str, Any]

DEFAULT_DAY_TRADE_CANDIDATES = [
    "HIVE",
    "SOFI",
    "RIOT",
    "MARA",
    "RIVN",
    "HOOD",
    "INTC",
    "WBD",
]


class DayTradeDataClient(Protocol):
    """KIS methods needed by the day-trade planner."""

    def get_price_detail(self, symbol: str) -> JsonObject:
        """Return current price detail fields."""

    def get_best_quote(self, symbol: str) -> JsonObject:
        """Return best bid/ask fields."""

    def get_overseas_buying_power(
        self,
        symbol: str,
        order_price: float | None = None,
    ) -> float:
        """Return symbol-specific overseas buying power."""


class DayTradeTradingClient(DayTradeDataClient, Protocol):
    """KIS methods needed to submit a guarded live order."""

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        ...

    def submit_order(self, order: OrderRequest) -> BrokerResponse:
        """Submit a broker order."""


class DayTradePlanError(ValueError):
    pass


class LiveOrderSafetyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DayTradeTestConfig:
    """Risk and filtering settings for the one-share test."""

    max_total_usd: float = MAX_TOTAL_USD
    qty: int = 1
    take_profit_pct: float = TAKE_PROFIT_PCT
    stop_loss_pct: float = STOP_LOSS_PCT
    max_hold_minutes: int = MAX_HOLD_MINUTES
    force_exit_minutes_before_close: int = FORCE_EXIT_MINUTES_BEFORE_CLOSE
    fee_buffer_usd: float = FEE_BUFFER_USD
    fee_buffer_pct: float = FEE_BUFFER_PCT
    min_volume: float = 500_000
    min_dollar_volume: float = 5_000_000
    min_day_range_pct: float = 1.5
    max_day_range_pct: float = 18.0
    max_abs_change_pct: float = 15.0
    max_spread_pct: float = 0.75
    min_quote_depth: float = 500
    confirmation_price_tolerance_pct: float = CONFIRMATION_PRICE_TOLERANCE_PCT
    record_path: Path = Path("logs/day_trade_test_orders.jsonl")


@dataclass(slots=True)  # noqa: MUTABLE_OK
class CandidateEvaluation:
    """One candidate symbol evaluation with exclusion reasons."""

    symbol: str
    eligible: bool
    name: str = ""
    exclude_reasons: list[str] = field(default_factory=list)
    last_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    buy_limit_price: float = 0.0
    spread_pct: float = 0.0
    bid_size: float = 0.0
    ask_size: float = 0.0
    volume: float = 0.0
    dollar_volume: float = 0.0
    day_range_pct: float = 0.0
    change_pct: float = 0.0
    estimated_required_amount: float = 0.0
    buying_power_checked: bool = False
    buying_power: float = 0.0
    one_share_affordable: bool = False
    score: float = 0.0

    def to_dict(self) -> JsonObject:
        """Return JSON-safe candidate diagnostics."""

        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, float):
                data[key] = round(value, 6)
        return data
