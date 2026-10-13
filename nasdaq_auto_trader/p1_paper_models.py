from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from math import isfinite

from .backtest_execution import PendingOrder
from .backtest_types import BacktestRejection, BacktestTrade, EquityPoint
from .entry_policy_experiment_models import EntryDecisionRecord
from .experimental_exit_models import ExitDiagnostics
from .models import Bar, Position
from .profitability_risk import AcceptedOrder, EntryConstraintRecord
from .sizing_entry_risk import SizingRecord


class PaperAccountError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class EntryRiskRecord:
    signal_timestamp: str
    symbol: str
    actual_decision_at: str
    equity: float
    risk_budget: float
    planned_risk: float
    initial_stop: float | None
    qty: int
    price: float
    expected_buy_fee: float
    expected_stop_sell_fee: float
    expected_adverse_cost: float


@dataclass(frozen=True, slots=True)
class PaperFillRecord:
    trade_index: int
    symbol: str
    side: str
    signal_timestamp: str
    actual_decision_at: str
    logical_session_open: str
    actual_computed_at: str
    simulated: bool = True


@dataclass(frozen=True, slots=True)
class StrategyState:
    entry_volatility: dict[str, float | None]
    filled_stops: dict[str, float]
    completed: dict[str, str]
    filled_qty: dict[str, float]
    session_qty: dict[str, float]
    accepted_timestamp: str
    risk_distance: dict[str, float]
    records: list[EntryDecisionRecord]
    exit_payload: str
    exit_diagnostics: dict[str, ExitDiagnostics]


@dataclass(frozen=True, slots=True)
class RiskState:
    timestamp: str
    day: str
    previous_equity: float
    day_start_equity: float
    day_halted: bool
    records: list[EntryConstraintRecord]
    accepted_orders: list[AcceptedOrder]
    sizing_records: list[SizingRecord]


@dataclass(frozen=True, slots=True)
class PaperState:
    version: int
    fingerprint: str
    starting_cash: float
    cash: float
    positions: dict[str, Position]
    pending: dict[str, PendingOrder]
    trades: list[BacktestTrade]
    rejections: list[BacktestRejection]
    entry_fees: dict[str, float]
    position_risk: dict[str, float]
    histories: dict[str, list[Bar]]
    processed: dict[str, str]
    equity_curve: list[EquityPoint]
    actual_decisions: dict[str, str]
    fill_records: list[PaperFillRecord]
    entry_risks: list[EntryRiskRecord]
    observed_at: str
    strategy: StrategyState
    risk: RiskState


def timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise PaperAccountError('timestamps must be valid ISO-8601 values') from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaperAccountError('timestamps must include a timezone')
    return parsed.astimezone(UTC)


def bar_identity(bar: Bar) -> str:
    return bar.symbol + '|' + timestamp(bar.timestamp).isoformat()


def bar_digest(bar: Bar) -> str:
    data = [bar.symbol, timestamp(bar.timestamp).isoformat(),
            float(bar.open), float(bar.high), float(bar.low), float(bar.close), float(bar.volume)]
    return sha256(dumps(data, allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def validate_bar(bar: Bar) -> None:
    timestamp(bar.timestamp)
    if not bar.symbol or not all(isfinite(v) and v > 0 for v in (bar.open, bar.high, bar.low, bar.close)):
        raise PaperAccountError('bar symbols and finite positive OHLC are required')
    if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close):
        raise PaperAccountError('inconsistent OHLC bounds')
    if not isfinite(bar.volume) or bar.volume < 0:
        raise PaperAccountError('bar volume must be finite and nonnegative')


def normalized_bar(bar: Bar) -> Bar:
    return Bar(bar.symbol, timestamp(bar.timestamp).isoformat(), float(bar.open),
               float(bar.high), float(bar.low), float(bar.close), float(bar.volume))
