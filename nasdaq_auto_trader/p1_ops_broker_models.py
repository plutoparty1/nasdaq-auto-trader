from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, Protocol, final

from .brokers.kis_reconciliation import KISOpenOrder, KISOrderHistory
from .entry_comparison import JsonValue
from .models import AccountSnapshot, OrderRequest, OrderSide, Position
from .p1_paper_protocol import STARTING_USD


class BrokerCredentials(Protocol):
    @property
    def paper(self) -> bool: ...


class OperatingBroker(Protocol):
    @property
    def credentials(self) -> BrokerCredentials: ...
    @property
    def account_fingerprint(self) -> str: ...
    def get_account(self, refresh: bool = False) -> AccountSnapshot: ...
    def list_positions(self, refresh: bool = False) -> dict[str, Position]: ...
    def get_overseas_buying_power(self, symbol: str, order_price: float | None = None) -> float: ...
    def bind_submission_window(self, order: OrderRequest, open_at: datetime, deadline: datetime) -> None: ...
    def submit_order(self, order: OrderRequest) -> dict[str, JsonValue]: ...
    def list_open_orders(self) -> tuple[KISOpenOrder, ...]: ...
    def list_order_history(self, start_date: str, end_date: str) -> tuple[KISOrderHistory, ...]: ...


@final
class OperatingError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class OrderState(StrEnum):
    PLANNED = 'planned'
    SUBMITTING = 'submitting'
    UNKNOWN = 'unknown'
    ACCEPTED = 'accepted'
    UNFILLED = 'unfilled'
    PARTIAL = 'partial'
    FILLED = 'filled'
    REJECTED = 'rejected'
    CANCELED = 'canceled'
    EXPIRED = 'expired'
    BLOCKED = 'blocked'


ACTIVE: Final = frozenset((OrderState.SUBMITTING, OrderState.UNKNOWN, OrderState.ACCEPTED,
                           OrderState.UNFILLED, OrderState.PARTIAL))
UNCERTAIN: Final = frozenset((OrderState.SUBMITTING, OrderState.UNKNOWN))


@dataclass(frozen=True, slots=True)
class Intent:
    key: str
    symbol: str
    side: OrderSide
    signal_at: str
    evaluated_at: str
    open_at: str
    close_at: str
    limit_price: float
    stop_price: float
    qty: int = 0
    state: OrderState = OrderState.PLANNED
    order_id: str = ''
    submitted_at: str = ''
    prior_order_ids: tuple[str, ...] = ()
    filled_qty: int = 0
    filled_notional: float = 0
    fee_estimate: float = 0
    cash_before: float = 0
    qty_before: float = 0
    awaiting_balance: bool = False
    reason: str = ''
    response_at: str = ''

    def request(self) -> OrderRequest:
        return OrderRequest(self.symbol, self.side, type='limit', time_in_force='day',
                            qty=float(self.qty), limit_price=self.limit_price)


@dataclass(frozen=True, slots=True)
class Holding:
    symbol: str
    qty: int
    average_price: float
    stop_price: float
    high_water_price: float
    mark_price: float
    entry_fee: float
    planned_risk: float

    def position(self) -> Position:
        return Position(self.symbol, float(self.qty), self.qty * self.mark_price,
                        self.average_price, self.high_water_price)


@final
class OperatingState:
    """Mutable durable accumulator of confirmed broker executions and pending intents."""

    def __init__(self) -> None:
        self.cash: float = STARTING_USD
        self.broker_start_cash: float = 0
        self.costs: float = 0
        self.realized: float = 0
        self.maximum_loss: float = 0
        self.peak_equity: float = STARTING_USD
        self.maximum_drawdown: float = 0
        self.previous_equity: float = STARTING_USD
        self.day_start_equity: float = STARTING_USD
        self.day: str = ''
        self.day_halted: bool = False
        self.observed_at: str = ''
        self.evaluated: dict[str, str] = {}
        self.holdings: dict[str, Holding] = {}
        self.intents: dict[str, Intent] = {}
        self.baseline: dict[str, Position] = {}
        self.initialized: bool = False
        self.blockers: list[str] = []
        self.faults: list[str] = []
        self.unsafe_symbols: list[str] = []
        self.protection_blockers: list[str] = []
        self.data_blockers: list[str] = []

    def equity(self) -> float:
        return self.cash + sum(p.qty * p.mark_price for p in self.holdings.values())

    def mark_loss(self, now: datetime) -> None:
        from zoneinfo import ZoneInfo

        equity = self.equity()
        day = now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        if self.day != day:
            self.day_start_equity = self.previous_equity
            self.day, self.day_halted = day, False
        self.day_halted |= equity <= self.day_start_equity * .98
        self.previous_equity = equity
        self.maximum_loss = max(self.maximum_loss, STARTING_USD - equity)
        self.peak_equity = max(self.peak_equity, equity)
        self.maximum_drawdown = max(self.maximum_drawdown, self.peak_equity - equity)
        self.observed_at = now.isoformat()
