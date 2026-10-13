import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal, assert_never

import pytest

from nasdaq_auto_trader.backtest import Backtester
from nasdaq_auto_trader.exit_experiment import EvaluationSplit
from nasdaq_auto_trader.experimental_exit_models import ExitPolicy
from nasdaq_auto_trader.models import Bar
from nasdaq_auto_trader.p1_paper_account import PaperAccount
from nasdaq_auto_trader.profitability_execution import ConservativeCosts
from nasdaq_auto_trader.profitability_experiment import ProfitabilityEvaluation
from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy
from nasdaq_auto_trader.sizing_entry_execution import DynamicExecutionBook
from nasdaq_auto_trader.sizing_entry_risk import DynamicEntryRisk
from nasdaq_auto_trader.strategy_config import StrategyConfig


def config() -> StrategyConfig:
    return StrategyConfig(buy_score=1, sell_score=99, long_sma=20,
                          use_regime_filter=False)


def bars(count: int = 74, price: float = 2) -> list[Bar]:
    start = datetime(2026, 1, 1, 21, tzinfo=UTC)
    return [Bar('TEST', (start + timedelta(days=i)).isoformat(),
                price, price + .1, price - .01, price + i * .001, 1000) for i in range(count)]


def account() -> PaperAccount:
    return PaperAccount(config(), ExitPolicy(), ConservativeCosts(quantity_step=1),
                        54.072814354631596)

def advance(target: PaperAccount, bar: Bar, *, allowed: bool = True, missed: bool = False) -> None:
    target.advance([bar], observed_at=bar.timestamp,
                   session_open_at=bar.timestamp.replace('21:00', '14:30'),
                   entries_allowed=allowed, missed_session=missed)


def test_warmup_retains_history_without_orders_or_equity() -> None:
    # Given a new empty account.
    target = account()
    # When completed indicator history is loaded.
    target.warmup({'TEST': bars()[:70]})
    # Then history advances without trading state.
    assert len(target.histories['TEST']) == 70
    assert not target.book.pending and not target.book.trades and not target.equity_curve
    assert not target.strategy.records and not target.risk.records


def test_restart_matches_uninterrupted_execution_with_pending_reservation() -> None:
    # Given a real P1 signal reserves cash on a new account.
    history = bars()
    target = account()
    target.warmup({'TEST': history[:70]})
    advance(target, history[70])
    assert target.book.pending and target.book.account(available=True).cash < target.book.cash
    recovered = account()
    # When the persisted pending decision is restored and both accounts continue.
    recovered.load_state(target.export_state())
    assert recovered.export_state() == target.export_state()
    for bar in history[71:]:
        advance(target, bar)
        advance(recovered, bar)
    # Then full ledger and continuation agree byte for byte.
    assert recovered.export_state() == target.export_state()
    assert recovered.result() == target.result()
    assert target.book.trades[0].qty > 1


def test_duplicate_retry_is_idempotent_and_conflicting_bar_is_rejected() -> None:
    # Given a completed bar already processed.
    target = account()
    bar = bars()[0]
    advance(target, bar)
    before = target.export_state()
    # When the same bar is retried and a revised close follows.
    advance(target, bar)
    with pytest.raises(ValueError):
        advance(target, replace(bar, close=2.001))
    # Then neither retry changes the ledger.
    assert target.export_state() == before


def test_actual_decision_clock_prevents_retroactive_open_fill() -> None:
    # Given a signal computed after the following session had already opened.
    history = bars()
    target = account()
    target.warmup({'TEST': history[:70]})
    target.advance([history[70]], observed_at=history[71].timestamp.replace('21:00', '15:00'),
                   session_open_at=history[70].timestamp.replace('21:00', '14:30'), entries_allowed=True)
    # When the following session's completed bar is ingested.
    advance(target, history[71])
    # Then no fill is invented at an open before the actual decision.
    assert not target.book.trades
    assert target.book.rejections[-1].reason == 'decision_not_before_session_open'


def test_missed_session_expires_pending_without_new_entry() -> None:
    # Given an accepted day order and a gap in observed sessions.
    history = bars()
    target = account()
    target.warmup({'TEST': history[:70]})
    advance(target, history[70])
    # When the caller classifies the next observed bar as missing a session.
    advance(target, history[72], missed=True)
    # Then the expired day order cannot fill or restart a buy.
    assert not target.book.trades and not target.book.pending
    assert target.book.rejections[-1].reason == 'missed_session_expired'


def test_incremental_path_matches_existing_p1_backtester() -> None:
    # Given identical daily synthetic data and real P1 components.
    history = bars()
    target = account()
    costs = target.costs
    strategy = ProfitabilityStrategy(config(), ExitPolicy())
    risk = DynamicEntryRisk(strategy, costs)
    split = EvaluationSplit('synthetic', history[0].timestamp, history[-1].timestamp)
    engine = Backtester(ProfitabilityEvaluation(strategy, risk, split, costs), risk,
        costs=costs, max_trade_risk_pct=.02, max_portfolio_risk_pct=.06,
        max_total_position_pct=.5, fill_observer=strategy, risk_includes_costs=True,
        execution_book_type=DynamicExecutionBook, on_book_created=risk.bind_book)
    expected = engine.run({'TEST': history}, target.starting_cash)
    # When the persistent account consumes one session at a time.
    for bar in history:
        advance(target, bar)
    # Then positions, fills, risk sizing, and equity match the existing engine.
    assert target.result() == expected
    assert target.risk.sizing_records == risk.sizing_records


def test_zero_quantity_is_preserved_and_stop_does_not_finalize_orders() -> None:
    # Given a valid signal whose one-share risk exceeds the fixed account budget.
    target = account()
    history = bars(price=20)
    target.warmup({'TEST': history[:70]})
    # When the account computes its first paper decision and a report is requested.
    advance(target, history[70])
    target.result()
    # Then no minimum-share exception or artificial EOF event appears.
    assert not target.book.pending and not target.book.trades and not target.book.rejections
    assert target.risk.sizing_records[-1].selected_qty == 0


@pytest.mark.parametrize('payload', ['{}', '{"version":NaN}', '{"version":1,"version":1}'])
def test_bad_state_is_rejected_without_mutating_account(payload: str) -> None:
    # Given a populated account and untrusted persisted input.
    target = account()
    advance(target, bars()[0])
    before = target.export_state()
    # When malformed or structurally incomplete JSON is restored.
    with pytest.raises(ValueError):
        target.load_state(payload)
    # Then the current state is preserved.
    assert target.export_state() == before



def test_restart_preserves_high_water_daily_halt_and_protective_pending() -> None:
    # Given an entry with a higher completed close followed by a stop breach.
    history = bars()
    target = account()
    target.warmup({'TEST': history[:70]})
    advance(target, history[70])
    advance(target, replace(history[71], high=2.4, close=2.2))
    advance(target, replace(history[72], open=1.8, low=1.7, high=1.85, close=1.75), allowed=False)
    assert target.risk.day_halted
    assert target.book.pending['TEST'].order.side == 'sell'
    # When a restart restores a protective pending order and daily halt.
    recovered = account()
    recovered.load_state(target.export_state())
    # Then retained stops, close-based high water, and halt survive exactly.
    assert recovered.export_state() == target.export_state()
    assert recovered.risk.day_halted
    assert recovered.book.positions['TEST'].high_water_price == 2.2
    assert recovered.strategy.exit_strategy is not None
    assert recovered.strategy.exit_strategy.state.positions['TEST'].high_water_price == 2.2


def test_gap_realized_loss_can_exceed_entry_budget_without_clipping() -> None:
    # Given a position and a close stop whose following session opens below the stop.
    history = bars()
    target = account()
    target.warmup({'TEST': history[:70]})
    advance(target, history[70])
    advance(target, history[71])
    advance(target, replace(history[72], open=1.8, low=1.7, high=1.85, close=1.75), allowed=False)
    # When the pending protective exit is simulated at the next admissible open.
    advance(target, replace(history[73], open=1.6, low=1.5, high=1.8, close=1.7), allowed=False)
    # Then actual loss remains larger than the planned two-percent budget.
    entry = target.entry_risks[0]
    sell = target.book.trades[-1]
    assert entry.planned_risk <= entry.risk_budget
    assert -sell.pnl > entry.risk_budget
    assert sell.pnl == pytest.approx((1.6 - 2) * sell.qty)
    evidence = target.fill_records[-1]
    assert evidence.simulated and evidence.actual_decision_at < evidence.logical_session_open
    assert evidence.actual_computed_at == history[73].timestamp


@pytest.mark.parametrize('mutation', ['cash_type', 'unknown', 'hash', 'clock', 'fingerprint', 'pending_qty', 'decision_future', 'curve_order'])
def test_structurally_corrupt_state_fails_without_mutation(mutation: Literal['cash_type', 'unknown', 'hash', 'clock', 'fingerprint', 'pending_qty', 'decision_future', 'curve_order']) -> None:
    # Given a real pending order serialized at a strict JSON boundary.
    target = account()
    target.warmup({'TEST': bars()[:70]})
    advance(target, bars()[70])
    before = target.export_state()
    raw = json.loads(before)
    match mutation:
        case 'cash_type':
            raw['cash'] = True
        case 'unknown':
            raw['unknown_field'] = 1
        case 'hash':
            raw['histories']['TEST'][0]['close'] = 2.001
        case 'clock':
            raw['actual_decisions']['TEST'] = '2026-01-01'
        case 'fingerprint':
            raw['fingerprint'] = 'different'
        case 'pending_qty':
            raw['pending']['TEST']['order']['qty'] = -1
        case 'decision_future':
            raw['actual_decisions']['TEST'] = '2030-01-01T00:00:00+00:00'
        case 'curve_order':
            raw['equity_curve'].append(raw['equity_curve'][0])
        case unreachable:
            assert_never(unreachable)
    # When a corrupted state is submitted.
    with pytest.raises(ValueError):
        target.load_state(json.dumps(raw))
    # Then the valid account remains intact.
    assert target.export_state() == before


def test_out_of_order_and_future_bars_are_rejected_atomically() -> None:
    # Given a valid account with a completed history.
    target = account()
    target.warmup({'TEST': bars()[:70]})
    advance(target, bars()[70])
    before = target.export_state()
    # When an unseen earlier symbol bar or a not-yet-completed bar is supplied.
    with pytest.raises(ValueError):
        advance(target, replace(bars()[69], symbol='OTHER'))
    with pytest.raises(ValueError):
        target.advance([bars()[71]], observed_at=bars()[70].timestamp,
                       session_open_at=bars()[70].timestamp, entries_allowed=True)
    # Then neither input mutates account state.
    assert target.export_state() == before


def test_manual_stop_keeps_pending_intent_without_eof_rejection() -> None:
    # Given an accepted entry waiting for the next actual session.
    target = account()
    target.warmup({'TEST': bars()[:70]})
    advance(target, bars()[70])
    before = target.export_state()
    # When the run stops and a result is requested repeatedly.
    target.result()
    target.result()
    # Then pending cash and risk reservations survive without synthetic rejection.
    assert target.book.pending and not target.book.rejections
    assert target.export_state() == before

def test_missed_history_appends_indicators_without_replaying_trading() -> None:
    # Given a pending entry before two missed sessions.
    history = bars(75)
    target = account()
    target.warmup({'TEST': history[:70]})
    advance(target, history[70])
    prior_result = target.result()
    prior_pending = dict(target.book.pending)
    # When missed bars are stored as indicator history before the current receipt.
    target.observe_missed_history({'TEST': history[71:73]})
    recovered = account()
    recovered.load_state(target.export_state())
    # Then import has no trades or equity and current processing expires the old order.
    assert recovered.result() == prior_result and recovered.book.pending == prior_pending
    assert recovered.histories['TEST'] == target.histories['TEST']
    advance(recovered, history[73], missed=True)
    assert len(recovered.equity_curve) == 2 and not recovered.book.trades
    assert len(recovered.histories['TEST']) == 74