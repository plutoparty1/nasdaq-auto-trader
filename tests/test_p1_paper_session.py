"""Synthetic calendar/session tests; no market data or profitability evidence."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nasdaq_auto_trader import p1_paper_session
from nasdaq_auto_trader.entry_comparison import JsonValue, load_entry_profile
from nasdaq_auto_trader.exit_experiment import candidates
from nasdaq_auto_trader.exit_experiment_config import ExperimentInputError
from nasdaq_auto_trader.exit_experiment_metrics import FxPoint
from nasdaq_auto_trader.models import Bar
from nasdaq_auto_trader.p1_paper_inputs import PaperReceipt
from nasdaq_auto_trader.p1_paper_protocol import (
    STARTING_USD,
    SYMBOLS,
    PaperProtocol,
    PaperSession,
)
from nasdaq_auto_trader.p1_paper_session import (
    account_status,
    apply_receipt,
    new_account_state,
    restore_accounts,
)
from nasdaq_auto_trader.profitability_execution import ConservativeCosts
from nasdaq_auto_trader.strategy_config import StrategyConfig


def protocol() -> PaperProtocol:
    begin = datetime(2026, 1, 1, 21, tzinfo=UTC)
    dates = [begin + timedelta(days=i) for i in range(250) if (begin + timedelta(days=i)).weekday() < 5]
    sessions = tuple(PaperSession(d.date().isoformat(), d.replace(hour=14).isoformat(), d.isoformat()) for d in dates)
    policy = next(item.policy for item in candidates() if item.name == 'fixed_8')
    assert policy is not None
    return PaperProtocol(Path('synthetic'), 'synthetic-sha', sessions[63].close_at,
                         load_entry_profile(Path('experiments/entry_policy/profile.json')), policy,
                         sessions, {'base': ConservativeCosts(.0025, 0, 10, 10, 1),
                                    'high_impact': ConservativeCosts(.0025, 0, 30, 30, 1)}, {})


def receipt(spec: PaperProtocol, index: int, identity: str) -> PaperReceipt:
    current = spec.sessions[index]
    bars = {symbol: [Bar(symbol, s.close_at, 3, 3.1, 2.9, 3, 1000)
                     for s in spec.sessions[:index+1]] for symbol in SYMBOLS}
    fx = FxPoint(current.day + 'T16:00:00+00:00', 1350)
    return PaperReceipt(identity, Path('synthetic-receipt'), bars, (fx,),
                        {symbol: current.close_at for symbol in SYMBOLS}, current.close_at, (), ())


def test_first_observation_fixes_sixty_sessions_and_new_krw() -> None:
    spec = protocol(); now = datetime.fromisoformat(spec.sessions[64].close_at) + timedelta(minutes=30)
    state = new_account_state(spec, now)
    apply_receipt(state, spec, receipt(spec, 64, 'one'), now)
    assert state['end_session'] == spec.sessions[123].day
    assert state['initial_krw'] == STARTING_USD * 1350
    assert state['initial_krw'] != 80000
    result = account_status(state, spec, now)
    assert result['elapsed_sessions'] == 1
    assert result['live_authorization'] is False


def test_duplicate_receipt_keeps_exact_checkpoint_payload() -> None:
    spec = protocol(); now = datetime.fromisoformat(spec.sessions[64].close_at) + timedelta(minutes=30)
    state = new_account_state(spec, now)
    item = receipt(spec, 64, 'one'); apply_receipt(state, spec, item, now)
    before = repr(state)
    assert apply_receipt(state, spec, item, now) is False
    assert repr(state) == before


def test_gap_counts_in_horizon_without_replaying_decisions() -> None:
    spec = protocol(); now = datetime.fromisoformat(spec.sessions[64].close_at) + timedelta(minutes=30)
    state = new_account_state(spec, now); apply_receipt(state, spec, receipt(spec, 64, 'one'), now)
    later = datetime.fromisoformat(spec.sessions[67].close_at) + timedelta(minutes=30)
    apply_receipt(state, spec, receipt(spec, 67, 'two'), later)
    result = account_status(state, spec, later)
    assert result['elapsed_sessions'] == 4
    assert result['data_fault_count'] == 1
    assert state['end_session'] == spec.sessions[123].day


def test_empty_initial_account_has_no_independent_performance_or_fake_fx() -> None:
    spec = protocol(); now = datetime.fromisoformat(spec.frozen_at)
    state = new_account_state(spec, now); result = account_status(state, spec, now)
    assert result['independent_evaluation_started'] is False
    assert result['starting_krw_at_evaluation'] is None
    assert result['initial_fx'] is None


def signal_protocol() -> PaperProtocol:
    return replace(protocol(), config=StrategyConfig(buy_score=1, sell_score=99,
                                                     use_regime_filter=False, long_sma=20))


def signal_receipt(spec: PaperProtocol, index: int) -> PaperReceipt:
    prices = {'CMCSA': 30.0, 'HIVE': 2.0, 'KDP': 40.0}
    histories = {symbol: [Bar(symbol, session.close_at, price, price + 1,
        price - .05, price + max(0, i - 64) * .01, 1000)
        for i, session in enumerate(spec.sessions[:index + 1])]
        for symbol, price in prices.items()}
    return replace(receipt(spec, index, f'session-{index}'), bars=histories)


def close_observation(spec: PaperProtocol, index: int) -> datetime:
    return datetime.fromisoformat(spec.sessions[index].close_at) + timedelta(minutes=30)


def started(spec: PaperProtocol) -> dict[str, JsonValue]:
    now = close_observation(spec, 64)
    state = new_account_state(spec, now)
    apply_receipt(state, spec, signal_receipt(spec, 64), now)
    return state


def test_status_exposes_combined_assessment_and_unfilled_by_cost_book() -> None:
    # Given two cost books that have accepted the same real synthetic entry.
    spec = signal_protocol()
    state = started(spec)
    now = close_observation(spec, 65)
    apply_receipt(state, spec, signal_receipt(spec, 65), now)
    # When manual status reports the still-open observation window.
    status = account_status(state, spec, now)
    # Then pending orders remain distinct and neither cost book is pooled.
    assert status['combined_assessment'] == 'observing'
    assert status['unfilled_orders'] == {
        'base': {'pending': 1, 'rejected_or_expired': 0},
        'high_impact': {'pending': 1, 'rejected_or_expired': 0}}
    assert status['cost_books_not_independent_samples'] is True


@pytest.mark.parametrize('fault', ['stale', 'missing_cohort'])
def test_bad_current_data_blocks_an_otherwise_valid_new_entry(fault: str) -> None:
    # Given a flat started account and a receipt that produces a real P1 signal.
    spec = signal_protocol()
    state = started(spec)
    current = signal_receipt(spec, 65)
    now = close_observation(spec, 65)
    timely = deepcopy(state)
    apply_receipt(timely, spec, current, now)
    assert all(account.book.pending for account in restore_accounts(timely, spec).values())
    if fault == 'stale':
        now = datetime.fromisoformat(spec.sessions[66].open_at) + timedelta(minutes=1)
    else:
        current = replace(current, bars={symbol: history[:-1] if symbol == 'KDP' else history
                                         for symbol, history in current.bars.items()})
    # When the same signal is observed after next open or with an incomplete cohort.
    apply_receipt(state, spec, current, now)
    # Then both scenario books block entries while retaining the observation.
    assert all(not account.book.pending and not account.book.trades
               for account in restore_accounts(state, spec).values())
    assert state['data_fault_count'] == 1


def test_fixed_window_counts_gaps_and_cannot_extend_after_session_sixty() -> None:
    # Given the first valid session fixed the end and all intermediate receipts were missed.
    spec = signal_protocol()
    state = started(spec)
    endpoint = close_observation(spec, 123)
    apply_receipt(state, spec, signal_receipt(spec, 123), endpoint)
    before = deepcopy(state['accounts'])
    # When a later receipt arrives after the frozen sixty-session endpoint.
    later = close_observation(spec, 124)
    apply_receipt(state, spec, signal_receipt(spec, 124), later)
    status = account_status(state, spec, later)
    # Then the account ends on schedule with insufficient evidence and no new trading state.
    assert state['end_session'] == spec.sessions[123].day
    assert state['accounts'] == before
    assert status['elapsed_sessions'] == 60 and status['phase'] == 'window_ended'
    assert status['combined_assessment'] == 'insufficient_observations'


def test_endpoint_without_terminal_receipt_is_insufficient() -> None:
    # Given the final session elapsed without a terminal observation.
    spec = signal_protocol()
    state = started(spec)
    # When status evaluates the fixed endpoint.
    status = account_status(state, spec, close_observation(spec, 123))
    # Then elapsed time cannot supply a missing terminal valuation.
    assert status['combined_assessment'] == 'insufficient_observations'
    scenarios = status['scenarios']
    assert isinstance(scenarios, dict)
    for summary in scenarios.values():
        assert isinstance(summary, dict)
        assert summary['outcome'] == 'insufficient_observations'
        reasons = summary['insufficient_reasons']
        assert isinstance(reasons, list) and 'missing_terminal_valuation' in reasons


def test_conflicting_bar_rejects_candidate_copy_without_changing_committed_state() -> None:
    # Given the same copy-on-write boundary used by the CLI before checkpoint publication.
    spec = signal_protocol()
    state = started(spec)
    before = deepcopy(state)
    candidate = deepcopy(state)
    current = signal_receipt(spec, 65)
    revised = dict(current.bars)
    revised['HIVE'] = [replace(bar, high=2.6) if i == 64 else bar
                       for i, bar in enumerate(revised['HIVE'])]
    # When a receipt attempts to revise an already committed bar.
    with pytest.raises(ExperimentInputError, match='observed_bar_revision'):
        apply_receipt(candidate, spec, replace(current, bars=revised), close_observation(spec, 65))
    # Then the caller can discard the candidate with both committed cost books intact.
    assert state == before and candidate['accounts'] == before['accounts']


def test_partial_cohort_still_submits_protection_for_valid_held_symbol() -> None:
    # Given both books hold HIVE and only the next KDP bar is missing.
    spec = signal_protocol()
    state = started(spec)
    for index in (65, 66):
        apply_receipt(state, spec, signal_receipt(spec, index), close_observation(spec, index))
    current = signal_receipt(spec, 67)
    histories = dict(current.bars)
    histories['KDP'] = histories['KDP'][:-1]
    histories['HIVE'] = [*histories['HIVE'][:-1], replace(histories['HIVE'][-1],
                          low=1.6, close=1.7)]
    # When the valid held symbol crosses its fixed stop in a partial cohort.
    apply_receipt(state, spec, replace(current, bars=histories), close_observation(spec, 67))
    # Then the data gate blocks buys while each protective sell covers its full holding.
    for account in restore_accounts(state, spec).values():
        assert account.book.pending['HIVE'].order.side == 'sell'
        assert account.book.pending['HIVE'].order.qty == account.book.positions['HIVE'].qty
        assert account.book.pending['HIVE'].decision.reasons == ['fixed_stop_loss']

@pytest.mark.parametrize(('base', 'high_impact', 'expected'), [
    ('further_review_candidate', 'further_review_candidate', 'further_review_candidate'),
    ('further_review_candidate', 'below_benchmark', 'below_benchmark'),
    ('below_benchmark', 'further_review_candidate', 'below_benchmark'),
    ('further_review_candidate', 'insufficient_observations', 'insufficient_observations'),
    ('insufficient_observations', 'insufficient_observations', 'insufficient_observations'),
])
def test_combined_assessment_requires_both_individual_scenario_results(
    base: str, high_impact: str, expected: str,
) -> None:
    # Given already evaluated scenario outcomes with separate sample counts.
    scenarios: dict[str, JsonValue] = {
        'base': {'outcome': base, 'completed_trades': 5 if base == 'insufficient_observations' else 10},
        'high_impact': {'outcome': high_impact, 'completed_trades': 5 if high_impact == 'insufficient_observations' else 10}}
    # When the endpoint outcomes are combined.
    outcome = p1_paper_session.assess_scenarios(scenarios)
    # Then only two candidate outcomes qualify and five-plus-five is never pooled.
    assert outcome == expected

def test_valid_protective_sell_fills_after_another_symbol_missed_prior_session() -> None:
    # Given a valid HIVE protective order submitted while CMCSA's bar is absent.
    spec = signal_protocol()
    state = started(spec)
    for index in (65, 66):
        apply_receipt(state, spec, signal_receipt(spec, index), close_observation(spec, index))
    partial = signal_receipt(spec, 67)
    histories = dict(partial.bars)
    histories['CMCSA'] = histories['CMCSA'][:-1]
    stop_bar = replace(histories['HIVE'][-1], low=1.6, close=1.7)
    histories['HIVE'] = [*histories['HIVE'][:-1], stop_bar]
    apply_receipt(state, spec, replace(partial, bars=histories), close_observation(spec, 67))
    assert all(account.book.pending['HIVE'].order.side == 'sell'
               for account in restore_accounts(state, spec).values())
    complete = signal_receipt(spec, 68)
    next_histories = dict(complete.bars)
    next_histories['HIVE'] = [*next_histories['HIVE'][:-2], stop_bar,
        replace(next_histories['HIVE'][-1], open=1.6, low=1.5, high=1.8, close=1.7)]
    # When all symbols return at the next scheduled session.
    apply_receipt(state, spec, replace(complete, bars=next_histories), close_observation(spec, 68))
    # Then the timely HIVE sell fills once at that open instead of expiring with CMCSA.
    for account in restore_accounts(state, spec).values():
        sells = [trade for trade in account.book.trades if trade.side == 'sell']
        assert len(sells) == 1 and sells[0].timestamp == spec.sessions[68].close_at, account.book.rejections
        assert 'HIVE' not in account.book.positions
        assert not account.book.rejections


def test_pending_order_expires_when_its_own_next_session_bar_is_missing() -> None:
    # Given a HIVE entry reserved for the next scheduled session.
    spec = signal_protocol()
    state = started(spec)
    apply_receipt(state, spec, signal_receipt(spec, 65), close_observation(spec, 65))
    partial = signal_receipt(spec, 66)
    histories = dict(partial.bars)
    histories['HIVE'] = histories['HIVE'][:-1]
    apply_receipt(state, spec, replace(partial, bars=histories), close_observation(spec, 66))
    # When HIVE returns one session after the order's eligible session was missed.
    apply_receipt(state, spec, signal_receipt(spec, 67), close_observation(spec, 67))
    # Then the old day order cannot fill at the later open.
    for account in restore_accounts(state, spec).values():
        assert not account.book.trades and not account.book.pending
        assert account.book.rejections[-1].reason == 'missed_session_expired'