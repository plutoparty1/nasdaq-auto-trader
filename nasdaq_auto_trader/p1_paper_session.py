"""One bounded manual observation; no scheduling, broker state or retrospective signals."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta

from .entry_comparison import JsonValue
from .exit_experiment_config import ExperimentInputError
from .exit_experiment_metrics import FxPoint
from .p1_paper_account import PaperAccount
from .p1_paper_inputs import PaperReceipt
from .p1_paper_metrics import paper_metrics
from .p1_paper_protocol import (
    STARTING_USD,
    SYMBOLS,
    PaperProtocol,
    mapping,
    text_field,
    utc,
)


def new_account_state(protocol: PaperProtocol, now: datetime) -> dict[str, JsonValue]:
    accounts: dict[str, JsonValue] = {}
    for name, costs in protocol.costs.items():
        accounts[name] = PaperAccount(protocol.config, protocol.policy, costs, STARTING_USD).export_state()
    return {'schema_version': 1, 'protocol_sha256': protocol.sha256,
            'created_at': now.isoformat(), 'accounts': accounts, 'initial_fx': None,
            'initial_fx_as_of': None, 'fx': {}, 'start_session': None, 'end_session': None,
            'last_session': None, 'receipt_ids': [], 'events': [], 'data_fault_count': 0}


def restore_accounts(state: dict[str, JsonValue], protocol: PaperProtocol) -> dict[str, PaperAccount]:
    if state.get('protocol_sha256') != protocol.sha256:
        raise ExperimentInputError('paper_protocol_drift_requires_new_account_version')
    accounts: dict[str, PaperAccount] = {}
    for name, costs in protocol.costs.items():
        account = PaperAccount(protocol.config, protocol.policy, costs, STARTING_USD)
        account.load_state(text_field(mapping(state.get('accounts')).get(name)))
        accounts[name] = account
    return accounts


def record_event(state: dict[str, JsonValue], now: datetime, reasons: list[str], *, fault: bool) -> None:
    events = state.get('events')
    count = state.get('data_fault_count')
    if not isinstance(events, list) or not isinstance(count, int):
        raise ExperimentInputError('paper_event_state_invalid')
    events.append({'recorded_at': now.isoformat(), 'reasons': list(reasons), 'data_fault': fault})
    state['data_fault_count'] = count + int(fault)


def apply_receipt(state: dict[str, JsonValue], protocol: PaperProtocol,
                  receipt: PaperReceipt, now: datetime) -> bool:
    """Return false for an identical receipt; never treat late history as timely decisions."""
    ids = state.get('receipt_ids')
    if not isinstance(ids, list):
        raise ExperimentInputError('paper_receipt_ids_invalid')
    if receipt.sha256 in ids:
        return False
    ids.append(receipt.sha256)
    completed = [i for i, s in enumerate(protocol.sessions) if utc(s.close_at) <= now]
    if not completed or completed[-1] + 1 >= len(protocol.sessions):
        raise ExperimentInputError('paper_calendar_range_unavailable')
    index = completed[-1]
    session, following = protocol.sessions[index:index + 2]
    if utc(session.close_at) <= utc(protocol.frozen_at):
        record_event(state, now, ['no_post_freeze_completed_session'], fault=False)
        return True
    end = state.get('end_session')
    if isinstance(end, str) and session.day > end:
        record_event(state, now, ['observation_window_ended_no_extension'], fault=False)
        return True
    current = [bar for history in receipt.bars.values() for bar in history if bar.timestamp == session.close_at]
    reasons = list(receipt.failures)
    if {bar.symbol for bar in current} != set(SYMBOLS):
        reasons.append('missing_current_cohort_data')
    if now >= utc(following.open_at):
        reasons.append('stale_close_after_next_open')
    valid_fx = [p for p in receipt.fx if utc(p.timestamp) <= now
                and now - utc(p.timestamp) <= timedelta(days=7)]
    if not valid_fx:
        reasons.append('missing_or_stale_fx')
    start = state.get('start_session')
    warmup = {symbol: [b for b in receipt.bars.get(symbol, []) if b.timestamp < session.close_at][-64:]
              for symbol in SYMBOLS}
    if any(day >= (start if isinstance(start, str) else session.day) for day in receipt.split_dates):
        reasons.append('corporate_split_requires_separate_review')
    checked_accounts = restore_accounts(state, protocol)
    for account in checked_accounts.values():
        for symbol, history in receipt.bars.items():
            known = {bar.timestamp: bar for bar in account.histories.get(symbol, [])}
            if any(bar.timestamp in known and bar != known[bar.timestamp] for bar in history):
                raise ExperimentInputError('paper_observed_bar_revision_requires_separate_review')
    if state.get('last_session') == session.day:
        record_event(state, now, ['already_processed_session_no_new_decision'], fault=False)
        return True
    if not isinstance(start, str):
        if any(len(history) < 64 for history in warmup.values()):
            reasons.append('insufficient_warmup')
        if reasons:
            record_event(state, now, reasons, fault=True)
            return True
        if index + 59 >= len(protocol.sessions):
            raise ExperimentInputError('paper_calendar_cannot_cover_sixty_sessions')
        state['pre_start_fault_count'] = state.get('data_fault_count', 0)
        state['data_fault_count'] = 0
        state['start_session'] = session.day
        state['end_session'] = protocol.sessions[index + 59].day
        state['initial_fx'] = valid_fx[-1].usdkrw
        state['initial_fx_as_of'] = valid_fx[-1].timestamp
        state['initial_krw'] = STARTING_USD * valid_fx[-1].usdkrw
    accounts = checked_accounts
    previous_day = state.get('last_session')
    missed = False
    if isinstance(previous_day, str):
        prior_index = next(i for i, s in enumerate(protocol.sessions) if s.day == previous_day)
        missing_symbol_history = any(not account.histories.get(symbol)
            or account.histories[symbol][-1].timestamp[:10] < previous_day
            for account in accounts.values() for symbol in SYMBOLS)
        missed = index > prior_index + 1
        if missing_symbol_history:
            reasons.append('prior_session_symbol_data_missing')
        if missed:
            reasons.append('missed_sessions_not_replayed_as_signals:' + str(index - prior_index - 1))
    if not current:
        record_event(state, now, reasons or ['no_current_data'], fault=True)
        return True
    current_symbols = {bar.symbol for bar in current}
    for account in accounts.values():
        for symbol, pending in tuple(account.book.pending.items()):
            if symbol not in current_symbols or pending.timestamp < protocol.sessions[index - 1].close_at:
                account.book.reject(pending, session.close_at, 'missed_session_expired')
                del account.book.pending[symbol]
                del account.actual_decisions[symbol]
        if not isinstance(previous_day, str):
            account.warmup(warmup)
        else:
            additional = {symbol: [bar for bar in receipt.bars.get(symbol, [])
                                   if (not account.histories.get(symbol) or
                                       account.histories[symbol][-1].timestamp < bar.timestamp)
                                   and bar.timestamp < session.close_at]
                          for symbol in SYMBOLS}
            if any(additional.values()):
                account.observe_missed_history(additional)
        account.advance(current, observed_at=now.isoformat(), session_open_at=session.open_at,
                        entries_allowed=not reasons, missed_session=missed)
    state['accounts'] = {name: account.export_state() for name, account in accounts.items()}
    state['last_session'] = session.day
    fx_map = mapping(state.get('fx'))
    for point in receipt.fx:
        old = fx_map.get(point.timestamp)
        if old is not None and old != point.usdkrw:
            raise ExperimentInputError('paper_fx_revision_requires_separate_revaluation')
        fx_map[point.timestamp] = point.usdkrw
    state['fx'] = fx_map
    record_event(state, now, reasons or ['completed_daily_observation_simulated_fills_only'], fault=bool(reasons))
    events = state['events']
    if isinstance(events, list):
        events.append({'receipt_sha256': receipt.sha256, 'event_close_at': session.close_at,
                       'received_at': dict(receipt.received_at), 'decision_computed_at': now.isoformat(),
                       'modeled_session_open_at': session.open_at,
                       'fill_evidence': 'daily_next_open_reconstruction_recorded_after_receipt'})
    return True


def assess_scenarios(scenarios: dict[str, JsonValue]) -> str:
    if set(scenarios) != {'base', 'high_impact'}:
        return 'insufficient_observations'
    outcomes = [mapping(scenario).get('outcome') for scenario in scenarios.values()]
    if any(outcome not in ('further_review_candidate', 'below_benchmark') for outcome in outcomes):
        return 'insufficient_observations'
    return ('further_review_candidate' if all(outcome == 'further_review_candidate' for outcome in outcomes)
            else 'below_benchmark')


def account_status(state: dict[str, JsonValue], protocol: PaperProtocol, now: datetime) -> dict[str, JsonValue]:
    accounts = restore_accounts(state, protocol)
    fx = tuple(FxPoint(stamp, float(rate)) for stamp, rate in sorted(mapping(state.get('fx')).items())
               if isinstance(rate, (float, int)) and not isinstance(rate, bool))
    initial = state.get('initial_fx')
    initial_fx = float(initial) if isinstance(initial, (int, float)) and not isinstance(initial, bool) else None
    end, start = state.get('end_session'), state.get('start_session')
    window = [s for s in protocol.sessions if isinstance(start, str) and isinstance(end, str) and start <= s.day <= end]
    elapsed = sum(utc(s.close_at) <= now for s in window)
    endpoint = bool(window and now >= utc(window[-1].close_at))
    count = state.get('data_fault_count', 0)
    if not isinstance(count, int):
        raise ExperimentInputError('paper_fault_count_invalid')
    summaries: dict[str, JsonValue] = {}
    for name, account in accounts.items():
        summaries[name] = paper_metrics(account, initial_fx=initial_fx, fx_history=fx,
            endpoint_reached=endpoint, data_fault_count=count, expected_sessions=elapsed,
            terminal_complete=state.get('last_session') == end and end is not None)
    combined = ('not_started' if not start else 'observing' if not endpoint else assess_scenarios(summaries))
    return {'profile': 'P1', 'protocol_sha256': protocol.sha256, 'frozen_at': protocol.frozen_at,
            'independent_evaluation_started': bool(start), 'starting_usd': STARTING_USD,
            'initial_fx': initial_fx, 'initial_fx_as_of': state.get('initial_fx_as_of'),
            'starting_krw_at_evaluation': state.get('initial_krw'), 'start_session': start,
            'fixed_end_session': end, 'elapsed_sessions': elapsed, 'target_sessions': 60,
            'phase': 'not_started' if not start else 'window_ended' if endpoint else 'observing',
            'cost_books_not_independent_samples': True, 'scenarios': summaries,
            'combined_assessment': combined,
            'combined_assessment_rule': 'both_cost_books_must_qualify_individually_no_pooled_samples',
            'unfilled_orders': {name: {'pending': len(account.book.pending),
                                      'rejected_or_expired': len(account.book.rejections)}
                                for name, account in accounts.items()},
            'pending': {name: [asdict(p) for p in account.book.pending.values()] for name, account in accounts.items()},
            'positions': {name: [asdict(p) for p in account.book.positions.values()] for name, account in accounts.items()},
            'data_fault_count': count, 'events': state.get('events', []),
            'order_api_calls': 0, 'cancel_api_calls': 0,
            'live_authorization': False, 'actual_account_fees': 'unverified'}
