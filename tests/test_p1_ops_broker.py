"""Synthetic confirmed-fill scenarios; all broker calls are in-memory."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path

from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.brokers.kis_reconciliation import KISOpenOrder, KISOrderHistory
from nasdaq_auto_trader.entry_comparison import JsonValue
from nasdaq_auto_trader.experimental_exit_models import ExitPolicy
from nasdaq_auto_trader.models import AccountSnapshot, Bar, OrderRequest, Position
from nasdaq_auto_trader.p1_paper_protocol import (
    STARTING_USD,
    PaperProtocol,
    PaperSession,
)
from nasdaq_auto_trader.profitability_execution import ConservativeCosts
from nasdaq_auto_trader.strategy_config import StrategyConfig


@dataclass(frozen=True, slots=True)
class Credentials:
    paper: bool = True


class FakeBroker:
    """Mutable in-memory broker keeps acceptance separate from confirmed execution."""

    def __init__(self) -> None:
        self.credentials = Credentials()
        self.account_fingerprint = 'synthetic-account'
        self.cash = 100.0
        self.positions: dict[str, Position] = {}
        self.open: tuple[KISOpenOrder, ...] = ()
        self.history: tuple[KISOrderHistory, ...] = ()
        self.submitted: list[OrderRequest] = []
        self.uncertain = False

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        return AccountSnapshot(self.cash, self.cash, self.cash)

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        return dict(self.positions)

    def get_overseas_buying_power(self, symbol: str, order_price: float | None = None) -> float:
        return self.cash

    def list_open_orders(self) -> tuple[KISOpenOrder, ...]:
        return self.open

    def list_order_history(self, start_date: str, end_date: str) -> tuple[KISOrderHistory, ...]:
        return self.history

    def bind_submission_window(self, order: OrderRequest, open_at: datetime, deadline: datetime) -> None:
        return None

    def submit_order(self, order: OrderRequest) -> dict[str, JsonValue]:
        self.submitted.append(order)
        if self.uncertain:
            raise BrokerRequestError('synthetic timeout')
        identifier = 'synthetic-order' if len(self.submitted) == 1 else 'synthetic-order-' + str(len(self.submitted))
        return {'rt_cd': '0', 'output': {'ODNO': identifier}}


def spec() -> PaperProtocol:
    begin = datetime(2026, 1, 1, 21, tzinfo=UTC)
    days = [begin + timedelta(days=i) for i in range(130)
            if (begin + timedelta(days=i)).weekday() < 5]
    sessions = tuple(PaperSession(d.date().isoformat(), d.replace(hour=14, minute=30).isoformat(),
                                  d.isoformat()) for d in days)
    return PaperProtocol(Path('synthetic'), 'synthetic-protocol', sessions[0].close_at,
        StrategyConfig(buy_score=1, sell_score=99, long_sma=20, use_regime_filter=False),
        ExitPolicy(), sessions, {'base': ConservativeCosts(.0025, 0, 10, 10, 1)}, {})


def sample_bars(protocol: PaperProtocol, index: int = 70) -> dict[str, list[Bar]]:
    return {'HIVE': [Bar('HIVE', s.close_at, 2, 2.1, 1.99, 2 + i * .001, 1000)
                     for i, s in enumerate(protocol.sessions[:index + 1])]}


def create(directory: Path, broker: FakeBroker, protocol: PaperProtocol):
    module = import_module('nasdaq_auto_trader.p1_ops_broker')
    assert hasattr(module, 'BrokerOperatingSession')
    session = module.BrokerOperatingSession(directory, protocol, broker,
        clock=lambda: datetime.fromisoformat(session.store.state.observed_at))
    return session


def prepare(directory: Path, broker: FakeBroker):
    protocol = spec()
    session = create(directory, broker, protocol)
    session.evaluate_completed(sample_bars(protocol), datetime.fromisoformat(protocol.sessions[70].close_at),
                               protocol.sessions[70], protocol.sessions[71], True)
    return session, protocol, datetime.fromisoformat(protocol.sessions[71].open_at)


def confirm(broker: FakeBroker, at: datetime, qty: float, *, reflected: bool = True,
            status: str = 'filled', price: float = 2.07) -> None:
    order = broker.submitted[0]
    assert order.qty is not None
    broker.history = (KISOrderHistory('synthetic-order', 'HIVE', 'buy', order.qty, qty,
                                     price, status, at),)
    if reflected:
        broker.positions['HIVE'] = Position('HIVE', qty, qty * price, price)
        broker.cash = 100 - qty * price - qty * price * .0025


def test_acceptance_does_not_create_holdings_when_broker_has_not_filled(tmp_path: Path) -> None:
    # Given a completed daily signal before the next session.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    assert not broker.submitted
    # When the next open accepts the saved order.
    session.tick(opened, True)
    # Then cash and ownership remain unchanged until authoritative history.
    assert len(broker.submitted) == 1
    assert session.status()['positions'] == []
    assert session.status()['cash_usd'] == STARTING_USD
    assert session.status()['orders'][0]['status'] == 'accepted'


def test_partial_fill_is_incremental_when_history_is_repeated(tmp_path: Path) -> None:
    # Given an accepted order with a partial execution.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    confirm(broker, opened, 2, status='unknown')
    # When reconciliation reads the same cumulative fill twice.
    session.tick(opened + timedelta(seconds=10), True)
    first = session.status()
    session.tick(opened + timedelta(seconds=20), True)
    # Then quantity and cost are applied exactly once.
    assert first['positions'][0]['qty'] == 2
    assert first['orders'][0]['status'] == 'partial'
    assert session.status()['cash_usd'] == first['cash_usd']
    assert session.status()['estimated_costs_usd'] == first['estimated_costs_usd']


def test_balance_lag_blocks_buys_when_history_precedes_account(tmp_path: Path) -> None:
    # Given a fill missing from the account balance response.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    confirm(broker, opened, 2, reflected=False, status='unknown')
    # When authoritative execution is reconciled.
    session.tick(opened + timedelta(seconds=10), True)
    # Then ownership exists but new entries remain blocked.
    assert session.status()['positions'][0]['qty'] == 2
    assert 'balance_lag' in session.status()['blockers']


def test_restart_keeps_submission_dedup_when_same_daily_signal_returns(tmp_path: Path) -> None:
    # Given an accepted persisted order.
    broker = FakeBroker()
    session, protocol, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    session.close()
    # When a new process sees the same signal and ticks again.
    resumed = create(tmp_path, broker, protocol)
    resumed.evaluate_completed(sample_bars(protocol), opened, protocol.sessions[70], protocol.sessions[71], True)
    resumed.tick(opened + timedelta(seconds=20), True)
    # Then acceptance is never retried.
    assert len(broker.submitted) == 1


def test_stale_entry_is_expired_when_next_open_window_was_missed(tmp_path: Path) -> None:
    # Given a plan saved before its target session.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    # When the process next runs after the permitted opening window.
    session.tick(opened + timedelta(minutes=6), True)
    # Then no delayed buy is submitted.
    assert not broker.submitted
    assert session.status()['orders'][0]['status'] == 'expired'


def test_existing_holdings_are_never_owned_or_managed(tmp_path: Path) -> None:
    # Given an unrelated preexisting position in the signal symbol.
    broker = FakeBroker()
    broker.positions['HIVE'] = Position('HIVE', 3, 6, 2)
    session, _, opened = prepare(tmp_path, broker)
    # When the P1 entry would otherwise be eligible.
    session.tick(opened, True)
    # Then it cannot add to or manage the unrelated holding.
    assert not broker.submitted
    assert session.status()['positions'] == []


def test_unknown_submission_does_not_adopt_unique_history_without_order_identity(tmp_path: Path) -> None:
    # Given a broker which accepted the request but lost its response.
    broker = FakeBroker()
    broker.uncertain = True
    session, _, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    assert 'unknown_submission' in session.status()['blockers']
    confirm(broker, opened, 2, status='unknown')
    # When a manual order could match the same symbol, quantity and submission time.
    session.tick(opened + timedelta(seconds=10), True)
    # Then no unproven ownership is adopted and no POST is repeated.
    assert len(broker.submitted) == 1
    assert session.status()['positions'] == []
    assert 'unknown_submission' in session.status()['blockers']
    assert session.status()['orders'][0]['reason'] == 'manual_order_identity_required'
