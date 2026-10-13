from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nasdaq_auto_trader.brokers.common import BrokerOrderRejected
from nasdaq_auto_trader.entry_comparison import JsonValue
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest, Position
from nasdaq_auto_trader.p1_ops_broker import BrokerOperatingSession
from nasdaq_auto_trader.p1_ops_broker_models import OperatingError
from nasdaq_auto_trader.p1_paper_protocol import STARTING_USD
from nasdaq_auto_trader.sizing_entry_execution import assess_quantity
from tests.test_p1_ops_broker import (
    Credentials,
    FakeBroker,
    confirm,
    create,
    prepare,
    sample_bars,
    spec,
)


class RejectingBroker(FakeBroker):
    def submit_order(self, order: OrderRequest) -> dict[str, JsonValue]:
        self.submitted.append(order)
        raise BrokerOrderRejected('synthetic-rejection')


def test_rejection_does_not_create_owned_shares(tmp_path: Path) -> None:
    # Given an order that the broker explicitly rejects.
    broker = RejectingBroker()
    session, _, opened = prepare(tmp_path, broker)
    # When the planned entry reaches its submission window.
    session.tick(opened, True)
    # Then rejection cannot debit cash or invent a position.
    assert session.status()['orders'][0]['status'] == 'rejected'
    assert session.status()['cash_usd'] == STARTING_USD
    assert session.status()['positions'] == []


def test_quantity_is_maximum_feasible_integer_using_frozen_costs(tmp_path: Path) -> None:
    # Given the frozen allocation and a fresh larger broker cash balance.
    broker = FakeBroker()
    session, protocol, opened = prepare(tmp_path, broker)
    # When the order is sized at submission.
    session.tick(opened, True)
    # Then the selected quantity passes every original cap and the next share fails.
    order = broker.submitted[0]
    assert order.qty is not None and order.limit_price is not None
    cash = AccountSnapshot(STARTING_USD, STARTING_USD, STARTING_USD)
    selected = assess_quantity(int(order.qty), order.limit_price, order.limit_price * .92,
                               protocol.costs['base'], cash, 0)
    next_share = assess_quantity(int(order.qty) + 1, order.limit_price, order.limit_price * .92,
                                 protocol.costs['base'], cash, 0)
    assert not selected.blockers
    assert next_share.blockers


def test_unknown_without_timestamp_stays_blocked(tmp_path: Path) -> None:
    # Given a lost submission response and history without provable submission time.
    broker = FakeBroker()
    broker.uncertain = True
    session, _, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    confirm(broker, opened, 2, reflected=False, status='unknown')
    broker.history = (replace(broker.history[0], submitted_at=None),)
    # When reconciliation cannot establish the order identity.
    session.tick(opened + timedelta(seconds=10), True)
    # Then no fill is adopted and the POST is not repeated.
    assert session.status()['positions'] == []
    assert 'unknown_submission' in session.status()['blockers']
    assert len(broker.submitted) == 1


def test_ambiguous_unknown_history_never_adopts_a_fill(tmp_path: Path) -> None:
    # Given two same-time candidate orders after an uncertain response.
    broker = FakeBroker()
    broker.uncertain = True
    session, _, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    confirm(broker, opened, 2, reflected=False, status='unknown')
    broker.history += (replace(broker.history[0], order_id='synthetic-other'),)
    # When history has no unique identity.
    session.tick(opened + timedelta(seconds=10), True)
    # Then rollback retains the durable unknown state.
    assert session.status()['positions'] == []
    assert 'unknown_submission' in session.status()['blockers']


def test_history_regression_does_not_undo_confirmed_execution(tmp_path: Path) -> None:
    # Given two confirmed shares already accounted for.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    confirm(broker, opened, 2, status='unknown')
    session.tick(opened + timedelta(seconds=10), True)
    cash = session.status()['cash_usd']
    broker.history = (replace(broker.history[0], filled_quantity=1),)
    # When stale history regresses cumulative quantity.
    with pytest.raises(OperatingError, match='regression'):
        session.tick(opened + timedelta(seconds=20), True)
    # Then committed quantity and cash remain intact.
    assert session.status()['positions'][0]['qty'] == 2
    assert session.status()['cash_usd'] == cash


def test_absent_open_order_does_not_prove_day_expiry(tmp_path: Path) -> None:
    # Given an accepted order with no authoritative terminal history.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    # When the process returns the following day and no open order is returned.
    session.tick(opened + timedelta(days=1), True)
    # Then it retains the unresolved order and never replays it.
    assert session.status()['orders'][0]['status'] == 'accepted'
    assert session.status()['pending_orders'] == 1
    assert len(broker.submitted) == 1


def test_missing_checkpoint_pointer_is_not_new_account(tmp_path: Path) -> None:
    # Given an existing durable operating ledger.
    broker = FakeBroker()
    session, protocol, _ = prepare(tmp_path, broker)
    session.close()
    (tmp_path / 'CURRENT').unlink()
    # When the pointer is missing on restart.
    with pytest.raises(OperatingError, match='pointer_missing'):
        create(tmp_path, broker, protocol)
    # Then restart fails without broker submission.
    assert not broker.submitted


def test_live_string_cannot_authorize_live_submission(tmp_path: Path) -> None:
    # Given real-mode transport without a per-order authorization callback.
    broker = FakeBroker()
    broker.credentials = Credentials(paper=False)
    protocol = spec()
    # When a caller requests an operating live adapter.
    with pytest.raises(OperatingError, match='p1_live_authorization_unavailable'):
        BrokerOperatingSession(tmp_path, protocol, broker, mode='kis_live')
    # Then the mode string provides no authorization.
    assert not broker.submitted


def test_external_ownership_change_is_sticky(tmp_path: Path) -> None:
    # Given a known untouched baseline after signal planning.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    broker.positions['CMCSA'] = Position('CMCSA', 1, 20, 20)
    session.tick(opened, True)
    broker.positions.clear()
    # When an external holding appears and is removed before another tick.
    session.tick(opened + timedelta(seconds=10), True)
    # Then the ownership incident remains blocked for review.
    assert 'external_ownership_change' in session.status()['blockers']
    assert not broker.submitted


def test_exit_uses_daily_close_even_when_entries_are_paused(tmp_path: Path) -> None:
    # Given a confirmed P1 holding with a completed close far below its stop.
    broker = FakeBroker()
    session, protocol, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    qty = broker.submitted[0].qty
    assert qty is not None
    confirm(broker, opened, qty)
    session.tick(opened + timedelta(seconds=10), True)
    history = sample_bars(protocol, 71)
    history['HIVE'][-1] = replace(history['HIVE'][-1], open=1.2, low=1.1, close=1.2)
    close = datetime.fromisoformat(protocol.sessions[71].close_at)
    # When the completed daily exit is evaluated with new entries paused.
    session.evaluate_completed(history, close, protocol.sessions[71], protocol.sessions[72], False)
    # Then the exit is saved for the following session and loss is not clipped at two percent.
    assert len(broker.submitted) == 1
    assert session.status()['orders'][-1]['side'] == 'sell'
    assert session.status()['orders'][-1]['status'] == 'planned'
    assert session.status()['maximum_observed_loss_usd'] > STARTING_USD * .02
