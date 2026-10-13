from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from math import floor, isfinite

from .brokers.kis_pricing import normalize_kis_limit_price
from .models import AccountSnapshot, Bar
from .p1_ops_broker_models import (
    ACTIVE,
    Intent,
    OperatingError,
    OrderState,
)
from .p1_ops_broker_store import OperatingStore
from .p1_paper_models import bar_digest, bar_identity, timestamp, validate_bar
from .p1_paper_protocol import SYMBOLS, PaperSession
from .sizing_entry_execution import assess_quantity


def validate_completed(store: OperatingStore, bars: dict[str, list[Bar]], observed: datetime,
                       session: PaperSession, following: PaperSession) -> None:
    close, opened = timestamp(session.close_at), timestamp(following.open_at)
    if observed.tzinfo is None or not close <= observed or not close < opened:
        raise OperatingError('invalid_completed_session_time')
    sessions = store.protocol.sessions
    try:
        index = sessions.index(session)
    except ValueError as error:
        raise OperatingError('unknown_signal_session') from error
    if index + 1 >= len(sessions) or sessions[index + 1] != following:
        raise OperatingError('next_regular_session_required')
    if not bars or not bars.keys() <= set(SYMBOLS):
        raise OperatingError('frozen_symbol_universe_required')
    for symbol, history in bars.items():
        if not history or timestamp(history[-1].timestamp) != close:
            raise OperatingError('completed_daily_close_required')
        previous = None
        for bar in history:
            validate_bar(bar)
            stamp = timestamp(bar.timestamp)
            if bar.symbol != symbol or stamp > close or (previous is not None and stamp <= previous):
                raise OperatingError('invalid_daily_history')
            if previous is not None and stamp.date() == previous.date():
                raise OperatingError('intraday_signal_forbidden')
            prior = store.codec.processed.get(bar_identity(bar))
            if prior is not None and prior != bar_digest(bar):
                raise OperatingError('conflicting_completed_history')
            previous = stamp


def plan_completed(store: OperatingStore, bars: dict[str, list[Bar]], observed: datetime,
                   session: PaperSession, following: PaperSession, entries_allowed: bool) -> None:
    validate_completed(store, bars, observed, session, following)
    state, strategy = store.state, store.codec.strategy
    if all(bar_identity(history[-1]) in state.evaluated for history in bars.values()):
        return
    incoming: dict[str, list[Bar]] = {}
    missed = False
    for symbol, history in bars.items():
        previous = store.codec.histories.get(symbol, [])
        incoming[symbol] = ([bar for bar in history if timestamp(bar.timestamp) > timestamp(previous[-1].timestamp)]
                            if previous else history[-65:])
        if previous:
            previous_day = timestamp(previous[-1].timestamp).date().isoformat()
            days = [item.day for item in store.protocol.sessions]
            missed |= previous_day not in days or days.index(session.day) - days.index(previous_day) > 1
    state.blockers = [reason for reason in state.blockers if reason not in state.data_blockers]
    state.data_blockers = (['missing_owned_daily_bar'] if state.holdings.keys() - bars.keys() else [])
    if missed:
        state.data_blockers.append('missed_completed_session')
    state.blockers = sorted(set(state.blockers + state.data_blockers))
    store.codec.observe_missed_history(incoming)
    for symbol in sorted(bars):
        history = store.codec.histories[symbol]
        bar = history[-1]
        key = bar_identity(bar)
        if key in state.evaluated:
            continue
        held = state.holdings.get(symbol)
        if held is not None:
            held = replace(held, mark_price=bar.close,
                           high_water_price=max(held.high_water_price, bar.close))
            state.holdings[symbol] = held
        state.mark_loss(observed)
        decision = strategy.evaluate(symbol, history, None if held is None else held.position(),
                                     evaluation_timestamp=bar.timestamp, completed_bar_id=bar.timestamp)
        state.evaluated[key] = bar_digest(bar)
        busy = any(intent.symbol == symbol and intent.state in ACTIVE | {OrderState.PLANNED}
                   for intent in state.intents.values())
        if busy or decision.action == 'hold':
            continue
        if decision.action == 'buy' and (not entries_allowed or state.day_halted or state.data_blockers
                or held is not None or symbol in state.baseline):
            continue
        if decision.action == 'sell' and held is None:
            continue
        price = float(normalize_kis_limit_price(Decimal(str(decision.latest_price)), decision.action))
        stop = strategy.initial_stop_for(symbol, price)
        if decision.action == 'buy' and (stop is None or not 0 < stop < price):
            continue
        intent = Intent(key, symbol, decision.action, bar.timestamp, observed.isoformat(),
            following.open_at, following.close_at, price, stop or 0)
        if observed >= timestamp(following.open_at):
            intent = replace(intent, state=OrderState.EXPIRED, reason='decision_after_target_open')
        state.intents[key] = intent


def quantity_for(store: OperatingStore, intent: Intent, account: AccountSnapshot,
                 buying_power: float) -> int:
    state, costs = store.state, store.protocol.costs['base']
    if not isfinite(buying_power) or buying_power < 0:
        return 0
    reserved = [item for item in state.intents.values() if item.state in ACTIVE and item.side == 'buy']
    reserved_cash = sum((item.qty - item.filled_qty) * item.limit_price
                        + costs.fee((item.qty - item.filled_qty) * item.limit_price) for item in reserved)
    isolated = AccountSnapshot(state.cash - reserved_cash, state.equity(),
        min(state.cash - reserved_cash, account.cash, account.buying_power, buying_power))
    # Risk is retained at initial stop; a trailing improvement cannot finance a larger entry.
    used_risk = sum(held.planned_risk for held in state.holdings.values())
    used_risk += sum(assess_quantity(item.qty - item.filled_qty, item.limit_price,
        item.stop_price, costs, isolated, 0).planned_risk for item in reserved if item.qty > item.filled_qty)
    bounded = replace(isolated, cash=min(isolated.cash, account.cash))
    if (not all(isfinite(value) and value >= 0 for value in
                (bounded.cash, bounded.equity, bounded.buying_power, used_risk))
            or intent.limit_price <= 0):
        return 0
    low, high = 0, floor(min(35, bounded.cash, bounded.buying_power, bounded.equity * .5) / intent.limit_price)
    while low < high:
        candidate = (low + high + 1) // 2
        if assess_quantity(candidate, intent.limit_price, intent.stop_price, costs, bounded, used_risk).blockers:
            high = candidate - 1
        else:
            low = candidate
    return low
