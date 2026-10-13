from __future__ import annotations

from dataclasses import replace
from math import isfinite
from typing import assert_never

from .brokers.kis_reconciliation import KISOrderHistory
from .p1_ops_broker_models import Holding, Intent, OperatingError
from .p1_ops_broker_store import OperatingStore
from .sizing_entry_execution import planned_loss


def apply_fill(store: OperatingStore, intent: Intent, row: KISOrderHistory) -> Intent:
    state, strategy, costs = store.state, store.codec.strategy, store.protocol.costs['base']
    values = (row.quantity, row.filled_quantity, row.average_fill_price)
    if (not all(isfinite(value) and value >= 0 for value in values)
            or not float(row.filled_quantity).is_integer()
            or not intent.filled_qty <= row.filled_quantity <= intent.qty):
        raise OperatingError('history_quantity_regression_or_invalid')
    total_qty = int(row.filled_quantity)
    notional = total_qty * row.average_fill_price
    if total_qty == intent.filled_qty:
        if abs(notional - intent.filled_notional) > 1e-7:
            raise OperatingError('history_price_revision')
        return intent
    delta_qty, delta_notional = total_qty - intent.filled_qty, notional - intent.filled_notional
    if row.average_fill_price <= 0 or delta_notional <= 0:
        raise OperatingError('history_fill_price_invalid')
    cumulative_fee = costs.fee(notional)
    delta_fee = cumulative_fee - intent.fee_estimate
    if delta_fee < -1e-9:
        raise OperatingError('history_fee_regression')
    held = state.holdings.get(intent.symbol)
    match intent.side:
        case 'buy':
            if held is not None and held.qty != intent.filled_qty:
                raise OperatingError('buy_ownership_conflict')
            average = notional / total_qty
            strategy.register_entry_fill(intent.symbol, average, float(total_qty), intent.submitted_at)
            stop = strategy.initial_stop_for(intent.symbol, average)
            if stop is None:
                raise OperatingError('confirmed_fill_stop_missing')
            retained_stop = stop if held is None else held.stop_price
            high = max(average, held.high_water_price if held else average)
            mark = delta_notional / delta_qty
            state.holdings[intent.symbol] = Holding(intent.symbol, total_qty, average,
                retained_stop, high, mark, cumulative_fee,
                planned_loss(total_qty, average, retained_stop, costs))
            state.cash -= delta_notional + delta_fee
        case 'sell':
            if held is None or delta_qty > held.qty:
                raise OperatingError('sell_ownership_conflict')
            remaining = held.qty - delta_qty
            released_fee = held.entry_fee * delta_qty / held.qty
            realized = delta_notional - held.average_price * delta_qty - released_fee - delta_fee
            state.realized += realized
            state.maximum_loss = max(state.maximum_loss, -realized)
            state.cash += delta_notional - delta_fee
            strategy.register_exit_fill(intent.symbol, float(remaining))
            if remaining:
                state.holdings[intent.symbol] = replace(held, qty=remaining,
                    entry_fee=held.entry_fee - released_fee,
                    planned_risk=planned_loss(remaining, held.average_price, held.stop_price, costs))
            else:
                del state.holdings[intent.symbol]
        case _:
            assert_never(intent.side)
    state.costs += delta_fee
    return replace(intent, filled_qty=total_qty, filled_notional=notional,
                   fee_estimate=cumulative_fee, awaiting_balance=True)
