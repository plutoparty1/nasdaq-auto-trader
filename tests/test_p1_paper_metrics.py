import json
from datetime import UTC, datetime, timedelta

import pytest

from nasdaq_auto_trader.ai_quant_lab.types import JsonObject, JsonValue
from nasdaq_auto_trader.backtest_types import BacktestTrade, EquityPoint
from nasdaq_auto_trader.exit_experiment_metrics import FxPoint
from nasdaq_auto_trader.experimental_exit_models import ExitPolicy
from nasdaq_auto_trader.models import Bar, Position
from nasdaq_auto_trader.p1_paper_account import PaperAccount
from nasdaq_auto_trader.p1_paper_metrics import paper_metrics
from nasdaq_auto_trader.p1_paper_models import EntryRiskRecord
from nasdaq_auto_trader.profitability_execution import ConservativeCosts
from nasdaq_auto_trader.strategy_config import StrategyConfig

CASH = 54.072814354631596


def account(curve: tuple[EquityPoint, ...] = (), trades: tuple[BacktestTrade, ...] = (),
            positions: tuple[Position, ...] = ()) -> PaperAccount:
    target = PaperAccount(StrategyConfig(), ExitPolicy(),
                          ConservativeCosts(commission_pct=.0025, quantity_step=1), CASH)
    target.equity_curve = list(curve)
    target.book.trades = list(trades)
    target.book.cash = curve[-1].cash if curve else CASH
    target.book.positions = {position.symbol: position for position in positions}
    target.histories = {symbol: [Bar(symbol, point.timestamp, price, price, price, price, 1000)
                                for point in curve]
                        for symbol, price in [('CMCSA', 30), ('HIVE', 5), ('KDP', 40)]}
    return target


def report(target: PaperAccount, *, endpoint: bool = False, initial_fx: float | None = 1400,
           fx_history: tuple[FxPoint, ...] | None = None, faults: int = 0,
           terminal: bool = True, expected: int | None = None) -> JsonObject:
    return paper_metrics(target, initial_fx=initial_fx,
        fx_history=tuple(FxPoint(point.timestamp, 1400) for point in target.equity_curve)
        if fx_history is None else fx_history, endpoint_reached=endpoint, data_fault_count=faults,
        expected_sessions=len(target.equity_curve) if expected is None else expected,
        terminal_complete=terminal)


def mapping(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def sequence(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def completed_account(count: int = 10, profit: float = .1) -> PaperAccount:
    start = datetime(2026, 1, 1, 21, tzinfo=UTC)
    times = [(start + timedelta(days=index)).isoformat() for index in range(count * 2 + 1)]
    trades = tuple(trade for index in range(count) for trade in (
        BacktestTrade(times[index * 2], times[index * 2 + 1], 'HIVE', 'buy', 5, 1, 5, ()),
        BacktestTrade(times[index * 2 + 1], times[index * 2 + 2], 'HIVE', 'sell',
                      5 + profit, 1, 5 + profit, (), pnl=profit)))
    target = account(tuple(EquityPoint(time, CASH + index // 2 * profit,
                                      CASH + index // 2 * profit, 0)
                           for index, time in enumerate(times)), trades)
    target.entry_risks = [EntryRiskRecord(trade.signal_timestamp, 'HIVE', trade.signal_timestamp,
        CASH, CASH * .02, .4, 4.6, 1, 5, 0, 0, 0) for trade in trades if trade.side == 'buy']
    return target


def test_not_started_has_no_performance_or_fabricated_krw() -> None:
    # Given a new dollar account with no FX receipt or equity observation.
    target = account()
    # When status is serialized under strict JSON rules.
    result = report(target, initial_fx=None)
    assert json.dumps(result, allow_nan=False)
    # Then no artificial KRW capital or performance is reported.
    assert result['status'] == 'not_started'
    assert result['starting_cash_usd'] == CASH
    assert result['starting_cash_krw'] is None and result['equity_krw'] is None
    assert result['independent_performance'] is None


def test_open_mark_to_market_includes_entry_costs_without_mutation() -> None:
    # Given an open share whose paid entry and current loss affect equity.
    buy = BacktestTrade('2026-01-01', '2026-01-02', 'HIVE', 'buy', 5.1, 1, 5.1, (),
                        fee=.2, execution_cost=.1)
    target = account((EquityPoint('2026-01-02', CASH - 1.3, CASH - 5.3, 4),),
                     (buy,), (Position('HIVE', 1, 4, 5.1),))
    before = target.export_state()
    # When independent performance is requested before the endpoint.
    result = report(target)
    details = mapping(result['independent_performance'])
    # Then open loss, exposure, and costs reconcile without an invented sell.
    assert details['net_pnl_usd'] == pytest.approx(-1.3)
    assert details['unrealized_pnl_after_entry_cost_usd'] == pytest.approx(-1.3)
    assert details['completed_roundtrips'] == 0 and result['outcome'] == 'observing'
    assert details['average_invested_pct'] == pytest.approx(400 / (CASH - 1.3))
    assert details['max_drawdown_pct'] == pytest.approx(-130 / CASH)
    assert mapping(sequence(details['trade_contributions'])[0])['net_pnl_usd'] == pytest.approx(-1.3)
    assert target.export_state() == before


def test_benchmark_is_fixed_whole_share_budget_and_zero_interest_cash() -> None:
    # Given aligned observations where only HIVE fits its equal initial budget.
    target = completed_account()
    # When executable comparators are computed.
    result = report(target)
    benchmarks = mapping(result['benchmarks'])
    hold = mapping(benchmarks['integer_buy_hold'])
    # Then a single affordable share is retained and fractional results are omitted.
    assert set(benchmarks) == {'usd_cash', 'integer_buy_hold'}
    assert hold['included_symbols'] == ['HIVE'] and hold['full_basket_available'] is False
    assert mapping(hold['performance'])['ending_equity_usd'] == pytest.approx(CASH - .0125)
    assert mapping(mapping(benchmarks['usd_cash'])['performance'])['ending_equity_usd'] == CASH


def test_gap_bars_are_excluded_from_benchmarks_and_prevent_positive_verdict() -> None:
    # Given an indicator bar absent from the evaluated account timestamps.
    target = completed_account()
    target.histories['HIVE'].append(Bar('HIVE', '2026-01-01T22:00:00+00:00', 99, 99, 99, 99, 1000))
    # When final status is evaluated.
    result = report(target, endpoint=True)
    hold = mapping(mapping(result['benchmarks'])['integer_buy_hold'])
    # Then the same evaluated timestamps are used and the gap is disclosed.
    assert len(sequence(hold['evaluated_timestamps'])) == len(target.equity_curve)
    assert result['unobserved_history_timestamps'] == ['2026-01-01T22:00:00+00:00']
    assert result['outcome'] == 'insufficient_observations'


@pytest.mark.parametrize('count,outcome', [(9, 'insufficient_observations'), (10, 'further_review_candidate')])
def test_minimum_completed_rule_is_administrative(count: int, outcome: str) -> None:
    # Given an otherwise complete positive account above both benchmarks.
    target = completed_account(count)
    # When the endpoint assessment is requested.
    result = report(target, endpoint=True)
    # Then ten completed trades only permit further review.
    assert result['outcome'] == outcome
    assert result['minimum_trade_rule'] == 'administrative_threshold_not_statistical_proof'


@pytest.mark.parametrize('faults,terminal,expected', [(1, True, None), (0, False, None), (0, True, 60)])
def test_faults_terminal_or_session_shortfall_fail_closed(faults: int, terminal: bool, expected: int | None) -> None:
    # Given a profitable sample with a deficient observation boundary.
    target = completed_account()
    # When endpoint evidence is assessed.
    result = report(target, endpoint=True, faults=faults, terminal=terminal, expected=expected)
    # Then profitability cannot override missing evidence.
    assert result['outcome'] == 'insufficient_observations'


@pytest.mark.parametrize('initial,history', [(None, ()), (1400, ()), (1400, (FxPoint('2025-12-01', 1400),))])
def test_missing_stale_or_constant_fx_has_no_krw_claim(initial: float | None, history: tuple[FxPoint, ...]) -> None:
    # Given dollar observations without valid initial and observation FX receipts.
    target = completed_account()
    # When output is serialized with nonfinite numbers forbidden.
    result = report(target, endpoint=True, initial_fx=initial, fx_history=history)
    assert json.dumps(result, allow_nan=False)
    # Then dollar metrics survive while KRW remains explicitly unknown.
    details = mapping(result['independent_performance'])
    assert details['cumulative_return_pct'] == pytest.approx(100 / CASH)
    assert details['cumulative_krw_return_pct'] is None and details['max_krw_drawdown_pct'] is None
    assert result['equity_krw'] is None and result['outcome'] == 'insufficient_observations'


def test_loss_uses_entry_signal_equity_and_embedded_execution_impact() -> None:
    # Given a completed losing trade whose costs are embedded in fill prices.
    buy = BacktestTrade('2026-01-01', '2026-01-02', 'HIVE', 'buy', 5.1, 1, 5.1, (), fee=.1, execution_cost=.1)
    sell = BacktestTrade('2026-01-02', '2026-01-03', 'HIVE', 'sell', 4.8, 1, 4.8, (),
                         pnl=-.5, fee=.1, allocated_entry_fee=.1, execution_cost=.1)
    target = account((EquityPoint('2026-01-03', CASH - .5, CASH - .5, 0),), (buy, sell))
    target.entry_risks = [EntryRiskRecord(buy.signal_timestamp, 'HIVE', buy.signal_timestamp,
        25, .5, .4, 4.9, 1, 5, .1, .1, .1)]
    # When closed risk and cost contributions are reported.
    details = mapping(report(target)['independent_performance'])
    trade = mapping(sequence(details['trade_contributions'])[0])
    # Then the realized loss reconciles exactly, without charging price impact twice.
    assert details['maximum_closed_trade_loss_usd'] == .5
    assert details['maximum_closed_trade_loss_pct_of_entry_signal_equity'] == 2
    assert details['planned_risk_exceed_count'] == 1
    assert trade['loss_reconciliation_usd'] == pytest.approx(.5)
    assert trade['planned_risk_excess_usd'] == pytest.approx(.1)
    assert trade['stop_to_exit_reference_move_usd'] == pytest.approx(0)
    assert trade['price_beyond_initial_stop_usd'] == pytest.approx(0)
    assert trade['delay_attributable_loss_usd'] is None
    assert details['commission_charge_count'] == details['execution_impact_charge_count'] == 2


def test_monthly_ten_percent_keeps_complete_and_partial_calendar_evidence_separate() -> None:
    # Given one full calendar month followed by a partial month, both gaining 10%.
    target = account((EquityPoint('2026-01-01', CASH, CASH, 0),
        EquityPoint('2026-01-31', CASH * 1.1, CASH * 1.1, 0),
        EquityPoint('2026-02-02', CASH * 1.21, CASH * 1.21, 0)))
    # When monthly statistics use the existing complete-calendar convention.
    details = mapping(report(target, faults=1)['independent_performance'])
    # Then partial months are not promoted to complete-month target evidence.
    assert details['target_complete_calendar_months'] == 1
    assert details['target_partial_calendar_months'] == 1
    assert details['missing_data_disclosed'] is True


@pytest.mark.parametrize('profit', [0, -.1])
def test_nonpositive_account_is_below_benchmark(profit: float) -> None:
    # Given enough observations and trades with no positive dollar return.
    target = completed_account(profit=profit)
    # When endpoint performance is assessed.
    result = report(target, endpoint=True)
    # Then the strategy cannot advance on the trade count alone.
    assert result['outcome'] == 'below_benchmark'


def test_krw_loss_is_reported_separately_from_fixed_usd_review_criterion() -> None:
    # Given a positive dollar account during a 10% decline in the dollar's KRW value.
    target = completed_account()
    fx = tuple(FxPoint(point.timestamp, 1260) for point in target.equity_curve)
    # When actual historical FX is supplied for every observation.
    result = report(target, endpoint=True, fx_history=fx)
    details = mapping(result['independent_performance'])
    # Then the fixed USD review criterion and the KRW loss are both transparent.
    assert result['outcome'] == 'further_review_candidate'
    assert details['ending_equity_krw'] == pytest.approx((CASH + 1) * 1260)
    assert details['cumulative_krw_return_pct'] == pytest.approx(((CASH + 1) * .9 / CASH - 1) * 100)
    assert details['max_krw_drawdown_pct'] == pytest.approx(-10)


def test_positive_return_below_executable_hold_does_not_advance() -> None:
    # Given the same observed endpoint where passive HIVE gains more than P1.
    target = completed_account()
    final = target.histories['HIVE'][-1]
    target.histories['HIVE'][-1] = Bar('HIVE', final.timestamp, 5, 50, 5, 50, 1000)
    # When the fixed comparators are assessed.
    result = report(target, endpoint=True)
    # Then positive P1 return alone cannot advance it to review.
    assert result['outcome'] == 'below_benchmark'


def test_missing_symbol_observation_never_changes_the_fixed_basket() -> None:
    # Given one frozen symbol is missing an evaluated observation.
    target = completed_account()
    target.histories['CMCSA'] = target.histories['CMCSA'][:-1]
    # When benchmarks are requested.
    result = report(target, endpoint=True)
    hold = mapping(mapping(result['benchmarks'])['integer_buy_hold'])
    # Then the comparator is unavailable rather than reallocating to two symbols.
    assert hold['performance'] is None
    assert result['benchmark_symbols'] == ['CMCSA', 'HIVE', 'KDP']
    assert result['outcome'] == 'insufficient_observations'
