from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from math import isfinite, nan
from typing import TYPE_CHECKING, Final

from .ai_quant_lab.types import JsonObject, JsonValue
from .backtest_types import BacktestResult, EquityPoint
from .entry_comparison_metrics import monthly_rows
from .exit_experiment import EvaluationSplit
from .exit_experiment_metrics import FxPoint, fx_at, summarize
from .p1_paper_trade_metrics import trade_diagnostics
from .profitability_benchmarks import build_benchmarks
from .profitability_metrics import additional_summary

if TYPE_CHECKING:
    from .p1_paper_account import PaperAccount

SYMBOLS: Final = ('CMCSA', 'HIVE', 'KDP')
MINIMUM_COMPLETED_TRADES: Final = 10


def _fresh_fx(timestamp: str, history: tuple[FxPoint, ...]) -> FxPoint | None:
    applicable = [point for point in history if point.timestamp <= timestamp]
    if not applicable:
        return None
    latest = applicable[-1]
    lag = (datetime.fromisoformat(timestamp).date()
           - datetime.fromisoformat(latest.timestamp).date()).days
    return latest if lag <= 7 else None


def _performance(
    result: BacktestResult, split: EvaluationSplit,
    initial_fx: float | None, fx_history: tuple[FxPoint, ...],
) -> tuple[JsonObject, int]:
    known = initial_fx is not None and all(
        _fresh_fx(point.timestamp, fx_history) is not None for point in result.equity_curve)
    performance = summarize(result, fx_rate=initial_fx if initial_fx is not None else nan,
                            operations_monthly_krw=None, fx_history=fx_history)
    extra = additional_summary(result, performance, split)
    values: JsonObject = asdict(performance.summary) | asdict(extra)
    rows: list[JsonObject] = [dict(row) for row in monthly_rows(performance, split)]
    if not known:
        for key in ('cumulative_krw_return_pct', 'max_krw_drawdown_pct',
                    'operations_cost_krw', 'after_operations_return_pct'):
            values[key] = None
        for row in rows:
            for key in ('ending_equity_krw', 'krw_return_pct', 'fx_only_return_pct',
                        'operations_cost_krw', 'after_operations_equity_krw'):
                row[key] = None
    for month, row in zip(performance.months, rows, strict=True):
        row['meets_usd_10pct'] = month.usd_return_pct >= 10 - 1e-9
        row['target_evidence'] = ('complete_calendar_window' if row['complete_calendar_window']
                                  else 'partial_calendar_window')
    values['fx_mode'] = 'historical_fx' if known else 'unknown_or_incomplete_fx'
    values['months'] = [row for row in rows]
    values['target_partial_calendar_months'] = sum(
        month.usd_return_pct >= 10 - 1e-9 and not row['complete_calendar_window']
        for month, row in zip(performance.months, rows, strict=True))
    values['ending_equity_usd'] = result.ending_value
    values['ending_equity_krw'] = (
        result.ending_value * fx_at(split.end, initial_fx, fx_history)
        if known and initial_fx is not None else None)
    return values, extra.completed_roundtrips


def paper_metrics(
    account: PaperAccount, *, initial_fx: float | None,
    fx_history: tuple[FxPoint, ...], endpoint_reached: bool, data_fault_count: int,
    expected_sessions: int, terminal_complete: bool,
) -> JsonObject:
    """Report one independent paper account without changing its execution state."""
    result = account.result()
    initial = initial_fx if initial_fx is not None and isfinite(initial_fx) and initial_fx > 0 else None
    history = tuple(sorted((point for point in fx_history
                            if isfinite(point.usdkrw) and point.usdkrw > 0),
                           key=lambda point: point.timestamp))
    timestamps = {point.timestamp for point in result.equity_curve}
    observed = len({timestamp[:10] for timestamp in timestamps})
    report: JsonObject = {
        'status': 'observing' if timestamps else 'not_started',
        'outcome': 'observing', 'starting_cash_usd': result.starting_cash,
        'starting_cash_krw': result.starting_cash * initial if initial is not None else None,
        'equity_usd': result.ending_value,
        'equity_krw': None, 'independent_performance': None, 'benchmarks': None,
        'observed_sessions': observed, 'expected_sessions': expected_sessions,
        'data_fault_count': data_fault_count, 'terminal_complete': terminal_complete,
        'endpoint_reached': endpoint_reached,
        'minimum_completed_trades': MINIMUM_COMPLETED_TRADES,
        'minimum_trade_rule': 'administrative_threshold_not_statistical_proof',
        'costs': asdict(account.costs), 'separate_ledger_state': True, 'independent_market_samples': False,
        'valuation': 'mark_to_market_including_entry_fees_no_forced_liquidation',
        'benchmark_symbols': list(SYMBOLS),
    }
    if not timestamps:
        if endpoint_reached:
            report['outcome'] = 'insufficient_observations'
        report['insufficient_reasons'] = ['no_equity_observations']
        return report
    split = EvaluationSplit('p1_paper', min(timestamps), max(timestamps))
    filtered = {symbol: [bar for bar in account.histories.get(symbol, [])
                         if bar.timestamp in timestamps] for symbol in SYMBOLS}
    aligned = all({bar.timestamp for bar in bars} == timestamps for bars in filtered.values())
    gaps = {bar.timestamp for symbol in SYMBOLS for bar in account.histories.get(symbol, [])
            if split.start <= bar.timestamp <= split.end and bar.timestamp not in timestamps}
    missing = not aligned or bool(gaps) or observed < expected_sessions or data_fault_count > 0
    performance, completed = _performance(result, split, initial, history)
    performance.update(trade_diagnostics(account, result))
    performance['missing_data_disclosed'] = missing
    report['independent_performance'] = performance
    report['equity_krw'] = performance['ending_equity_krw']
    report['unobserved_history_timestamps'] = [timestamp for timestamp in sorted(gaps)]
    report['benchmark_data_aligned'] = aligned
    latest_fx = _fresh_fx(split.end, history)
    report['valuation_fx_asof'] = latest_fx.timestamp if latest_fx is not None else None
    report['valuation_fx_lag_days'] = (
        (datetime.fromisoformat(split.end).date() - datetime.fromisoformat(latest_fx.timestamp).date()).days
        if latest_fx is not None else None)
    cash_result = BacktestResult(result.starting_cash, result.starting_cash, equity_curve=tuple(
        EquityPoint(point.timestamp, result.starting_cash, result.starting_cash, 0)
        for point in result.equity_curve))
    cash: JsonObject = {'status': 'USD_CASH_INTEREST_ZERO',
                        'performance': _performance(cash_result, split, initial, history)[0]}
    hold: JsonObject = {'status': 'insufficient_aligned_data', 'performance': None}
    hold_return: float | None = None
    if aligned:
        cases = build_benchmarks(filtered, split, account.costs, result.starting_cash)
        case = cases['integer_buy_hold']
        hold_return = case.result.return_pct
        feasibility: list[JsonValue] = []
        for item in case.feasibility.symbols:
            row: JsonObject = asdict(item)
            row['blocking_reasons'] = [reason for reason in item.blocking_reasons]
            feasibility.append(row)
        hold = {
            'status': case.status, 'performance': _performance(case.result, split, initial, history)[0],
            'included_symbols': list(case.included_symbols), 'missing_symbols': list(case.missing_symbols),
            'full_basket_available': case.feasibility.full_basket_available,
            'feasibility': feasibility,
            'full_basket_one_share_outlay_usd': case.feasibility.full_basket_one_share_outlay_usd,
            'full_basket_required_initial_cash_usd': case.feasibility.full_basket_required_initial_cash_usd,
            'notes': list(case.notes),
            'evaluated_timestamps': [timestamp for timestamp in sorted(timestamps)],
        }
        cash['performance'] = _performance(cases['usd_cash'].result, split, initial, history)[0]
    report['benchmarks'] = {'usd_cash': cash, 'integer_buy_hold': hold}
    reasons: list[JsonValue] = []
    if completed < MINIMUM_COMPLETED_TRADES:
        reasons.append('fewer_than_10_completed_trades')
    if missing:
        reasons.append('data_fault_or_missing_sessions')
    if not terminal_complete:
        reasons.append('missing_terminal_valuation')
    if performance['ending_equity_krw'] is None:
        reasons.append('unknown_or_incomplete_fx')
    if hold_return is None:
        reasons.append('benchmark_unavailable')
    report['insufficient_reasons'] = reasons
    if endpoint_reached:
        report['status'] = 'completed'
        report['outcome'] = ('insufficient_observations' if reasons else
                             'further_review_candidate' if hold_return is not None
                             and result.return_pct > max(0.0, hold_return)
                             else 'below_benchmark')
    return report
