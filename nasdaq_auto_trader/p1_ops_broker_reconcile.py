from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from math import isfinite
from typing import Final, Literal, assert_never

from .brokers.kis_reconciliation import KISOpenOrder, KISOrderHistory
from .models import AccountSnapshot, Position
from .p1_ops_broker_fills import apply_fill
from .p1_ops_broker_models import (
    ACTIVE,
    UNCERTAIN,
    Intent,
    OperatingBroker,
    OperatingError,
    OrderState,
)
from .p1_ops_broker_store import OperatingStore
from .p1_paper_models import timestamp

HISTORY_STATES: Final[dict[str, Literal['rejected', 'canceled', 'filled', 'active']]] = {
    'rejected': 'rejected', 'canceled': 'canceled', 'cancelled': 'canceled', 'filled': 'filled',
    'unknown': 'active', 'accepted': 'active', 'partial': 'active',
    'partially_filled': 'active', 'unfilled': 'active',
}


def matching_history(intent: Intent, rows: tuple[KISOrderHistory, ...]) -> KISOrderHistory | None:
    if not intent.order_id:
        return None
    submitted = timestamp(intent.submitted_at)
    latest = (timestamp(intent.response_at) + timedelta(seconds=2) if intent.response_at
              else submitted + timedelta(seconds=30))
    if latest < submitted:
        raise OperatingError('invalid_submission_response_clock')
    same_id = [row for row in rows if row.order_id == intent.order_id]
    matches = [row for row in same_id if row.submitted_at is None or
        (row.submitted_at.tzinfo is not None
         and submitted - timedelta(seconds=2) <= row.submitted_at <= latest)]
    if same_id and not matches:
        raise OperatingError('order_history_timestamp_mismatch')
    if len(matches) > 1:
        raise OperatingError('ambiguous_order_history')
    if not matches:
        return None
    row = matches[0]
    if (not row.is_original_order or (row.symbol, row.side, row.quantity)
            != (intent.symbol, intent.side, intent.qty)):
        raise OperatingError('order_history_identity_mismatch')
    return row


def reconcile_intent(store: OperatingStore, intent: Intent, rows: tuple[KISOrderHistory, ...],
                     opens: tuple[KISOpenOrder, ...]) -> Intent:
    if not intent.order_id:
        return replace(intent, state=OrderState.UNKNOWN, reason='manual_order_identity_required')
    row = matching_history(intent, rows)
    if row is not None:
        history_state = HISTORY_STATES.get(row.status)
        if history_state is None:
            raise OperatingError('unsupported_history_status')
        if (intent.state == OrderState.CANCELED and history_state != 'canceled'
                or intent.state == OrderState.REJECTED and history_state != 'rejected'):
            raise OperatingError('terminal_history_regression')
        intent = apply_fill(store, intent, row)
        intent = replace(intent, order_id=row.order_id, reason='')
        match history_state:
            case 'rejected':
                if intent.filled_qty:
                    raise OperatingError('rejected_order_has_fills')
                return replace(intent, state=OrderState.REJECTED)
            case 'canceled':
                return replace(intent, state=OrderState.CANCELED)
            case 'filled':
                if intent.filled_qty != intent.qty:
                    raise OperatingError('incomplete_filled_order')
                return replace(intent, state=OrderState.FILLED)
            case 'active':
                if intent.filled_qty == intent.qty:
                    return replace(intent, state=OrderState.FILLED)
                return replace(intent, state=OrderState.PARTIAL if intent.filled_qty else OrderState.UNFILLED)
            case _:
                assert_never(history_state)
    matched_open = [item for item in opens if intent.order_id and item.order_id == intent.order_id]
    if len(matched_open) > 1:
        raise OperatingError('ambiguous_open_order')
    if matched_open:
        item = matched_open[0]
        if (item.symbol, item.side, item.quantity, item.limit_price) != (
                intent.symbol, intent.side, intent.qty, intent.limit_price):
            raise OperatingError('open_order_identity_mismatch')
        if item.filled_quantity > intent.filled_qty:
            return replace(intent, reason='fill_history_pending')
        return replace(intent, state=OrderState.PARTIAL if intent.filled_qty else OrderState.UNFILLED)
    return intent


def reconcile_balances(store: OperatingStore, account: AccountSnapshot,
                       positions: dict[str, Position]) -> list[str]:
    state = store.state
    blockers = [*state.faults, *state.data_blockers]
    state.protection_blockers = list(state.unsafe_symbols)
    if not state.initialized:
        state.baseline, state.initialized = dict(positions), True
        state.broker_start_cash = account.cash
    gross_flow = sum(item.filled_notional * (1 if item.side == 'sell' else -1)
                     for item in state.intents.values())
    expected_cash = state.broker_start_cash + gross_flow
    reflected_cash = expected_cash - state.costs - 1e-7 <= account.cash <= expected_cash + 1e-7
    if not reflected_cash:
        pending_cash = any(item.state in ACTIVE or item.awaiting_balance for item in state.intents.values())
        blockers.append('cash_reconciliation_pending' if pending_cash else 'external_cash_change')
    for key, intent in tuple(state.intents.items()):
        if not intent.awaiting_balance:
            continue
        actual = positions.get(intent.symbol)
        observed_qty = 0 if actual is None else actual.qty
        direction = 1 if intent.side == 'buy' else -1
        expected_qty = intent.qty_before + direction * intent.filled_qty
        if abs(observed_qty - expected_qty) <= 1e-7 and reflected_cash:
            state.intents[key] = replace(intent, awaiting_balance=False)
        else:
            blockers.append('balance_lag')
            state.protection_blockers.append(intent.symbol)
    for symbol in state.baseline.keys() | state.holdings.keys() | positions.keys():
        baseline, held, actual = state.baseline.get(symbol), state.holdings.get(symbol), positions.get(symbol)
        expected = (baseline.qty if baseline else 0) + (held.qty if held else 0)
        actual_qty = actual.qty if actual else 0
        lagging = [item for item in state.intents.values()
                   if item.symbol == symbol and item.awaiting_balance]
        allowed_lag = any(min(item.qty_before, expected) <= actual_qty <= max(item.qty_before, expected)
                          for item in lagging)
        pending = [item for item in state.intents.values() if item.symbol == symbol and item.state in ACTIVE]
        awaiting_history = any(min(item.qty_before, item.qty_before + (item.qty if item.side == 'buy' else -item.qty))
            <= actual_qty <= max(item.qty_before, item.qty_before + (item.qty if item.side == 'buy' else -item.qty))
            for item in pending)
        if abs(actual_qty - expected) > 1e-7 and awaiting_history and not allowed_lag:
            blockers.append('fill_history_pending')
            state.protection_blockers.append(symbol)
        if abs(actual_qty - expected) > 1e-7 and not allowed_lag and not awaiting_history:
            blockers.append('external_ownership_change')
            state.unsafe_symbols.append(symbol)
        if actual and not lagging and abs(actual_qty - expected) <= 1e-7:
            expected_average = held.average_price if held else baseline.avg_entry_price if baseline else 0
            if abs(actual.avg_entry_price - expected_average) > max(.0001, expected_average * .0001):
                blockers.append('external_ownership_change')
                state.unsafe_symbols.append(symbol)
            if held and actual.market_value > 0:
                state.holdings[symbol] = replace(held, mark_price=actual.market_value / actual.qty)
    if any(item.state in UNCERTAIN for item in state.intents.values()):
        blockers.append('unknown_submission')
        state.protection_blockers.extend(item.symbol for item in state.intents.values() if item.state in UNCERTAIN)
    if any(item.reason == 'fill_history_pending' for item in state.intents.values() if item.state in ACTIVE):
        blockers.append('fill_history_pending')
    if 'external_ownership_change' in blockers and 'external_ownership_change' not in state.faults:
        state.faults.append('external_ownership_change')
    state.unsafe_symbols = sorted(set(state.unsafe_symbols))
    state.protection_blockers = sorted(set(state.protection_blockers + state.unsafe_symbols))
    return sorted(set(blockers))


def reconcile(store: OperatingStore, broker: OperatingBroker, now: datetime,
              ) -> tuple[AccountSnapshot, dict[str, Position], tuple[str, ...]]:
    account = broker.get_account(refresh=True)
    positions = broker.list_positions(refresh=True)
    if not all(isfinite(value) and value >= 0 for value in (account.cash, account.equity, account.buying_power)):
        raise OperatingError('invalid_broker_balance')
    for symbol, pos in positions.items():
        if (symbol != pos.symbol or not all(isfinite(value) for value in
            (pos.qty, pos.market_value, pos.avg_entry_price)) or pos.qty <= 0 or pos.avg_entry_price <= 0):
            raise OperatingError('invalid_broker_position')
    opens = broker.list_open_orders()
    submitted = [item for item in store.state.intents.values() if item.submitted_at]
    earliest = min((timestamp(item.submitted_at) for item in submitted), default=now) - timedelta(days=1)
    rows = broker.list_order_history(earliest.strftime('%Y%m%d'), (now + timedelta(days=1)).strftime('%Y%m%d'))
    for key, intent in tuple(store.state.intents.items()):
        if intent.submitted_at and not (intent.state == OrderState.REJECTED and not intent.order_id):
            store.state.intents[key] = reconcile_intent(store, intent, rows, opens)
    blockers = reconcile_balances(store, account, positions)
    known = {item.order_id for item in store.state.intents.values() if item.order_id}
    if any(item.order_id not in known for item in opens):
        blockers.append('external_open_order')
        store.state.protection_blockers.extend(item.symbol for item in opens if item.order_id not in known)
    store.state.blockers = sorted(set(blockers))
    store.state.mark_loss(now)
    return account, positions, tuple(sorted({row.order_id for row in rows} | {row.order_id for row in opens}))
