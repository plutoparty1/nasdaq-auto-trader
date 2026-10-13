from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nasdaq_auto_trader.brokers.kis_reconciliation import KISOrderHistory
from nasdaq_auto_trader.models import Position
from tests.test_p1_ops_broker import FakeBroker, confirm, prepare, sample_bars


@pytest.mark.parametrize('partial_buy', [False, True])
def test_crossed_buy_and_sell_reconcile_aggregate_cash_flows(tmp_path: Path, partial_buy: bool) -> None:
    # Given a confirmed owned holding and overlapping next-session BUY and SELL intents.
    broker = FakeBroker()
    session, protocol, opened = prepare(tmp_path, broker)
    session.tick(opened, True)
    confirm(broker, opened, 2, status='canceled')
    session.tick(opened + timedelta(seconds=10), True)
    history = sample_bars(protocol, 71)
    history['CMCSA'] = [replace(bar, symbol='CMCSA') for bar in history['HIVE']]
    history['HIVE'][-1] = replace(history['HIVE'][-1], open=3, high=3.1, low=2.9, close=3)
    session.evaluate_completed(history, datetime.fromisoformat(protocol.sessions[71].close_at),
                               protocol.sessions[71], protocol.sessions[72], True)
    broker.positions['HIVE'] = replace(broker.positions['HIVE'], market_value=6)
    target = datetime.fromisoformat(protocol.sessions[72].open_at)
    session.tick(target, True)
    assert len(broker.submitted) == 3
    buy, sell = broker.submitted[1:]
    assert buy.side == 'buy' and sell.side == 'sell'
    assert buy.qty is not None and buy.limit_price is not None
    assert sell.qty is not None and sell.limit_price is not None
    buy_qty = buy.qty - 1 if partial_buy else buy.qty
    buy_notional, sell_notional = buy_qty * buy.limit_price, sell.qty * sell.limit_price
    prior_cash = broker.cash
    broker.cash += sell_notional * .9975 - buy_notional * 1.0025
    del broker.positions['HIVE']
    broker.positions['CMCSA'] = Position('CMCSA', buy_qty, buy_notional, buy.limit_price)
    broker.history += (
        KISOrderHistory('synthetic-order-2', 'CMCSA', 'buy', buy.qty, buy_qty, buy.limit_price,
                        'unknown' if partial_buy else 'filled', target),
        KISOrderHistory('synthetic-order-3', 'HIVE', 'sell', sell.qty, sell.qty, sell.limit_price,
                        'filled', target),
    )
    # When both opposite cash movements are reflected in one broker snapshot.
    session.tick(target + timedelta(seconds=10), True)
    # Then aggregate cash and resulting quantities release the balance gate.
    assert 'balance_lag' not in session.status()['blockers']
    assert session.status()['positions'][0]['symbol'] == 'CMCSA'
    assert session.status()['positions'][0]['qty'] == buy_qty
    assert broker.cash > prior_cash - buy_notional
    if partial_buy:
        broker.cash -= buy.limit_price * 1.0025
        broker.positions['CMCSA'] = Position('CMCSA', buy.qty, buy.qty * buy.limit_price, buy.limit_price)
        broker.history = (broker.history[0], replace(broker.history[1], filled_quantity=buy.qty, status='filled'),
                          broker.history[2])
        session.tick(target + timedelta(seconds=20), True)
        assert 'balance_lag' not in session.status()['blockers']
        assert session.status()['positions'][0]['qty'] == buy.qty


@pytest.mark.parametrize('cash_change', [-5.0, 5.0])
def test_external_cash_change_blocks_entries_without_adopting_funds(tmp_path: Path, cash_change: float) -> None:
    # Given a saved plan and a broker cash movement unrelated to any owned fill.
    broker = FakeBroker()
    session, _, opened = prepare(tmp_path, broker)
    prior = session.status()['cash_usd']
    broker.cash += cash_change
    # When reconciliation cannot explain the deposit or withdrawal from confirmed executions.
    session.tick(opened, True)
    # Then new buys are blocked and the isolated allocation is unchanged.
    assert 'external_cash_change' in session.status()['blockers']
    assert not broker.submitted
    assert session.status()['cash_usd'] == prior
