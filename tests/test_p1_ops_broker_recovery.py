from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nasdaq_auto_trader import p1_ops_broker_store
from nasdaq_auto_trader.entry_comparison import JsonValue
from nasdaq_auto_trader.models import Position
from nasdaq_auto_trader.p1_ops_broker_models import OperatingError
from nasdaq_auto_trader.p1_paper_models import normalized_bar
from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy
from tests.test_p1_ops_broker import (
    FakeBroker,
    confirm,
    create,
    prepare,
    sample_bars,
    spec,
)


def test_first_daily_decision_uses_sixty_four_warmup_bars(tmp_path: Path) -> None:
    # Given provider history longer than the frozen warmup.
    broker = FakeBroker()
    session, protocol, _ = prepare(tmp_path, broker)
    expected = ProfitabilityStrategy(protocol.config, protocol.policy)
    history = [normalized_bar(bar) for bar in sample_bars(protocol)['HIVE'][-65:]]
    # When the independent strategy evaluates the exact frozen warmup plus signal bar.
    expected.decide('HIVE', history, None)
    # Then indicator input identity and decisions match the operating strategy.
    assert len(session.store.codec.histories['HIVE']) == 65
    assert session.store.codec.strategy.records == expected.records


def test_rolling_provider_window_keeps_accumulated_history(tmp_path: Path) -> None:
    # Given a first completed decision with retained strategy history.
    broker = FakeBroker()
    session, protocol, _ = prepare(tmp_path, broker)
    rolling = {'HIVE': sample_bars(protocol, 71)['HIVE'][-20:]}
    # When a short overlapping provider window supplies the next close.
    session.evaluate_completed(rolling, datetime.fromisoformat(protocol.sessions[71].close_at),
                               protocol.sessions[71], protocol.sessions[72], False)
    # Then the seed and earlier bars remain available to the strategy.
    assert len(session.store.codec.histories['HIVE']) == 66


def test_gap_blocks_new_entries_but_retains_completed_history(tmp_path: Path) -> None:
    # Given a first daily decision consumed while entry permission is paused.
    protocol, broker = spec(), FakeBroker()
    session = create(tmp_path, broker, protocol)
    session.evaluate_completed(sample_bars(protocol), datetime.fromisoformat(protocol.sessions[70].close_at),
                               protocol.sessions[70], protocol.sessions[71], False)
    # When the next observation skips an entire completed signal session.
    session.evaluate_completed(sample_bars(protocol, 72), datetime.fromisoformat(protocol.sessions[72].close_at),
                               protocol.sessions[72], protocol.sessions[73], True)
    # Then history advances but an unexpected gap cannot replay a late entry.
    assert 'missed_completed_session' in session.status()['blockers']
    assert session.status()['orders'] == []


def test_save_failure_before_post_does_not_submit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a durable entry plan and an unavailable intent checkpoint write.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    original = p1_ops_broker_store.write_checkpoint

    def write(directory: Path, state: dict[str, JsonValue], previous: str | None) -> str:
        if 'submitting' in repr(state):
            raise OSError('synthetic unavailable disk')
        return original(directory, state, previous)

    monkeypatch.setattr(p1_ops_broker_store, 'write_checkpoint', write)
    # When persisting the intent fails before the broker call.
    with pytest.raises(OSError):
        session.tick(opened, True)
    # Then no POST occurs and memory restores the previously committed plan.
    assert not broker.submitted
    assert session.status()['orders'][0]['status'] == 'planned'


def test_save_failure_after_post_restores_unknown_durable_intent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given a broker acceptance followed by a failing response checkpoint.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    original = p1_ops_broker_store.write_checkpoint

    def write(directory: Path, state: dict[str, JsonValue], previous: str | None) -> str:
        if "'state': 'accepted'" in repr(state):
            raise OSError('synthetic unavailable disk')
        return original(directory, state, previous)

    monkeypatch.setattr(p1_ops_broker_store, 'write_checkpoint', write)
    # When publication fails after POST has returned.
    with pytest.raises(OSError):
        session.tick(opened, True)
    # Then the durable submitting intent blocks another buy immediately.
    assert len(broker.submitted) == 1
    assert 'unknown_submission' in session.status()['blockers']


def test_balance_before_history_blocks_without_adopting_or_latching_external_fault(tmp_path: Path) -> None:
    # Given acceptance with a balance movement that history has not yet confirmed.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    broker.positions['HIVE'] = Position('HIVE', 2, 4.14, 2.07)
    broker.cash = 95.84
    # When the broker balance arrives before the original fill history.
    session.tick(opened + timedelta(seconds=10), True)
    # Then the discrepancy waits for history without inventing ownership.
    assert session.status()['positions'] == []
    assert 'fill_history_pending' in session.status()['blockers']
    assert 'external_ownership_change' not in session.status()['blockers']


def test_owned_exit_submits_while_unrelated_external_change_blocks_entries(tmp_path: Path) -> None:
    # Given a confirmed holding and an exit plan computed from its daily close.
    broker = FakeBroker()
    session, protocol, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    qty = broker.submitted[0].qty
    assert qty is not None
    confirm(broker, opened, qty)
    session.tick(opened + timedelta(seconds=10), True)
    history = sample_bars(protocol, 71)
    history['HIVE'][-1] = replace(history['HIVE'][-1], open=1.2, low=1.1, close=1.2)
    session.evaluate_completed(history, datetime.fromisoformat(protocol.sessions[71].close_at),
                               protocol.sessions[71], protocol.sessions[72], False)
    broker.positions['CMCSA'] = Position('CMCSA', 1, 20, 20)
    # When the next open occurs with entries paused and unrelated ownership changed.
    session.tick(datetime.fromisoformat(protocol.sessions[72].open_at), False)
    # Then the confirmed P1 holding can still receive its daily protection order.
    assert len(broker.submitted) == 2
    assert broker.submitted[-1].side == 'sell'


def test_partial_then_canceled_keeps_only_confirmed_quantity(tmp_path: Path) -> None:
    # Given a partially filled order with authoritative remainder cancellation.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    confirm(broker, opened, 2, status='canceled')
    # When the cancellation and fills are reconciled twice.
    session.tick(opened + timedelta(seconds=10), True)
    first = session.status()
    session.tick(opened + timedelta(seconds=20), True)
    # Then the owned quantity and fees stay fixed while the order becomes terminal.
    assert session.status()['positions'][0]['qty'] == 2
    assert session.status()['orders'][0]['status'] == 'canceled'
    assert session.status()['estimated_costs_usd'] == first['estimated_costs_usd']
    assert session.status()['pending_orders'] == 0


def test_canceled_history_cannot_regress_to_active(tmp_path: Path) -> None:
    # Given an authoritative cancellation already committed.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    confirm(broker, opened, 2, status='canceled')
    session.tick(opened + timedelta(seconds=10), True)
    broker.history = (replace(broker.history[0], status='unknown'),)
    # When later history loses the cancellation evidence.
    with pytest.raises(OperatingError, match='terminal_history_regression'):
        session.tick(opened + timedelta(seconds=20), True)
    # Then the durable cancellation and confirmed shares remain intact.
    assert session.status()['orders'][0]['status'] == 'canceled'


def test_later_partial_fill_updates_weighted_average_and_total_fee_once(tmp_path: Path) -> None:
    # Given an initial partial execution at one price.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    confirm(broker, opened, 1, status='unknown', price=2)
    session.tick(opened + timedelta(seconds=10), True)
    confirm(broker, opened, 2, status='unknown', price=2.03)
    # When cumulative history adds a second share at a different execution price.
    session.tick(opened + timedelta(seconds=20), True)
    # Then ownership uses the broker weighted average and the cumulative order fee.
    assert session.status()['positions'][0]['qty'] == 2
    assert session.status()['positions'][0]['average_price'] == 2.03
    assert session.status()['estimated_costs_usd'] == pytest.approx(4.06 * .0025)
    assert session.store.codec.strategy._filled_qty['HIVE'] == 2
