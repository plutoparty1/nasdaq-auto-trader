"""Twelve frozen offline profiles through the existing execution and metric engines."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

from .backtest import Backtester
from .backtest_types import BacktestRejection
from .entry_comparison import JsonValue, _write_rows
from .entry_comparison_inputs import build_splits
from .entry_comparison_metrics import monthly_rows
from .exit_experiment import EvaluationSplit, validate_daily_bars
from .exit_experiment_config import CostScenario, ExperimentInputError
from .exit_experiment_metrics import FxPoint, fx_at, summarize
from .models import Bar, Position, TradeDecision
from .profitability_benchmarks import build_benchmarks
from .profitability_config import FROZEN_PROFILE_SHA, RISK_BUDGETS, frozen_candidates
from .profitability_execution import ConservativeCosts
from .profitability_metrics import additional_summary
from .profitability_risk import AcceptedOrder, ProfitabilityRisk
from .profitability_strategy import ProfitabilityStrategy
from .strategy_config import StrategyConfig


class ProfitabilityEvaluation:
    def __init__(self, strategy: ProfitabilityStrategy, risk: ProfitabilityRisk,
                 split: EvaluationSplit, costs: ConservativeCosts) -> None:
        self.strategy, self.risk, self.split, self.costs = strategy, risk, split, costs

    def decide(self, symbol: str, bars: list[Bar], position: Position | None) -> TradeDecision:
        self.risk.timestamp = bars[-1].timestamp
        if bars[-1].timestamp < self.split.start:
            return TradeDecision(symbol, 'hold', 0, bars[-1].close, ['warmup_no_orders'])
        decision = self.strategy.decide(symbol, bars, position)
        if decision.action != 'buy' or decision.risk_per_share is None:
            return decision
        stop = decision.latest_price - decision.risk_per_share
        expected_cost = self.costs.fee(decision.latest_price) + self.costs.fee(stop)
        expected_cost += (decision.latest_price + stop) * self.costs.adverse_fraction
        return replace(decision, risk_per_share=decision.risk_per_share + expected_cost)


def run_profitability_suite(
    config: StrategyConfig, bars: dict[str, list[Bar]], splits: tuple[EvaluationSplit, ...],
    output: Path, costs: tuple[CostScenario, ...], *, fx_rate: float,
    manifest: dict[str, JsonValue], profile_path: Path,
    fx_history: tuple[FxPoint, ...] = (), operations_monthly_krw: float | None = None,
) -> None:
    policies = frozen_candidates(profile_path, manifest)
    validate_daily_bars(bars)
    if manifest.get('assessment') != 'SYNTHETIC_SMOKE_ONLY':
        expected = build_splits(bars, '2025-08-29T23:59:59+00:00', '2026-02-27T23:59:59+00:00')
        if splits != expected:
            raise ExperimentInputError('evaluation windows differ from the frozen protocol')
    if operations_monthly_krw is not None:
        raise ExperimentInputError('frozen experiment leaves unverified operating charges unknown')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ExperimentInputError('output must be empty; prior results are preserved')
    manifest = dict(manifest)
    if manifest.get('assessment') != 'SYNTHETIC_SMOKE_ONLY':
        manifest['assessment'] = 'EXPLORATORY_ALREADY_USED_DATA'
    manifest['profitability_profile_sha256'] = FROZEN_PROFILE_SHA
    manifest['no_independent_holdout'] = True
    manifest['limitations'] = [
        'Original A/B/C used 1%; these twelve C-entry profiles use 1%, 2%, 4% trade risk with fixed one-share cap',
        'All historical windows and the hindsight-selected cohort are development/exploratory data',
        'Close-only protective observation and next-open execution cannot validate intraday stops or limit queue fills',
        'Modelled commissions and impact are assumptions; exact account levies, FX conversion and operations fees unverified',
        'Whole-share passive benchmark can omit unaffordable constituents; fractional full basket is nonexecutable',
        'Dividend cash omitted; overlap audited separately; open equity included; no monthly extrapolation from intraday data',
    ]
    protocol = {
        'frozen_profile': json.loads(profile_path.read_text(encoding='utf-8')),
        'profiles': [{'name': f'{item.name}_risk{int(risk * 100)}',
                          'policy': None if item.policy is None else asdict(item.policy), 'risk_pct': risk}
                     for item in policies for risk in RISK_BUDGETS],
        'strategy': asdict(config), 'costs': [asdict(item) for item in costs],
        'splits': [asdict(item) for item in splits], 'manifest': manifest,
        'execution': 'next_open_adverse_cost_limit_positive_volume; close-only protective observation',
    }
    protocol['sha256'] = hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()
    (output / 'protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    names = ('summary', 'monthly', 'fills', 'reasons', 'equity', 'constraints',
             'orders', 'order_rejections', 'decisions', 'blockers', 'benchmarks',
             'benchmark_monthly', 'benchmark_equity', 'benchmark_fills', 'benchmark_feasibility')
    tables: dict[str, list[dict[str, JsonValue]]] = {name: [] for name in names}
    for split in splits:
        prefix = {symbol: [bar for bar in history if bar.timestamp <= split.end]
                  for symbol, history in bars.items()}
        split_fx = fx_at(split.start, fx_rate, fx_history)
        fx_stamp = next((point.timestamp for point in reversed(fx_history)
                         if point.timestamp <= split.start), str(manifest.get('fx_as_of', '')))
        for scenario in costs:
            cost = ConservativeCosts(scenario.commission_pct, scenario.minimum_commission,
                                     scenario.spread_bps, scenario.slippage_bps, 1)
            _benchmarks(prefix, split, cost, split_fx, fx_history, scenario.name, tables)
            for candidate in policies:
                for risk_pct in RISK_BUDGETS:
                    strategy = ProfitabilityStrategy(config, candidate.policy)
                    risk = ProfitabilityRisk(strategy, cost, risk_pct)
                    adapter = ProfitabilityEvaluation(strategy, risk, split, cost)
                    result = Backtester(adapter, risk, costs=cost, max_trade_risk_pct=risk_pct,
                                        max_portfolio_risk_pct=.06, max_total_position_pct=.5,
                                        fill_observer=strategy, risk_includes_costs=True).run(
                                            prefix, starting_cash=80000 / split_fx)
                    result = replace(result, equity_curve=tuple(
                        point for point in result.equity_curve if point.timestamp >= split.start))
                    performance = summarize(result, fx_rate=split_fx, fx_history=fx_history,
                                            operations_monthly_krw=None)
                    records = [record for record in risk.records if record.timestamp >= split.start]
                    key: dict[str, JsonValue] = {'split': split.name, 'profile': f'{candidate.name}_risk{int(risk_pct * 100)}',
                           'policy': candidate.name, 'risk_pct': risk_pct, 'cost_scenario': scenario.name}
                    submitted_buys = count_submitted_buys(risk.accepted_orders, result.rejections)
                    tables['summary'].append({**key, **asdict(performance.summary),
                            **asdict(additional_summary(result, performance, split)),
                            'starting_krw': 80000, 'starting_usd': result.starting_cash,
                            'initial_usdkrw': split_fx, 'fx_as_of': fx_stamp,
                            'raw_entry_signals': sum(row.entry_condition_met for row in records),
                            'eligible_entry_signals': sum(row.action == 'buy' for row in records),
                            'order_candidates': len(risk.accepted_orders),
                            'submitted_buy_orders': submitted_buys,
                            'risk_budget_blocked_signals': sum(row.entry_condition_met
                                and 'trade_risk_budget' in row.blocking_conditions for row in records),
                            'max_filled_buy_qty': max((trade.qty for trade in result.trades if trade.side == 'buy'), default=0),
                            'assessment': manifest['assessment'],
                        })
                    tables['monthly'].extend(key | row for row in monthly_rows(performance, split))
                    for name, entries in (('fills', result.trades), ('reasons', performance.reasons),
                                          ('equity', result.equity_curve), ('constraints', records),
                                          ('orders', risk.accepted_orders), ('order_rejections', result.rejections),
                                          ('decisions', strategy.records)):
                        tables[name].extend(key | asdict(row) for row in entries)
                    first = Counter(row.first_reason for row in records)
                    all_conditions = Counter(reason for row in records for reason in row.blocking_conditions)
                    signal_conditions = Counter(reason for row in records if row.entry_condition_met
                                                for reason in row.blocking_conditions)
                    for reason in sorted(first.keys() | all_conditions.keys()):
                        tables['blockers'].append(key | {'reason': reason,
                            'first_count': first[reason], 'all_condition_count': all_conditions[reason],
                            'buy_signal_condition_count': signal_conditions[reason]})
    for name, rows in tables.items():
        _write_rows(output / f'{name}.csv', rows)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def _benchmarks(
    bars: dict[str, list[Bar]], split: EvaluationSplit, cost: ConservativeCosts,
    split_fx: float, fx_history: tuple[FxPoint, ...], scenario: str,
    tables: dict[str, list[dict[str, JsonValue]]],
) -> None:
    cases = build_benchmarks(bars, split, cost, 80000 / split_fx)
    for name, case in (('usd_cash', cases['usd_cash']), ('integer_buy_hold', cases['integer_buy_hold']),
                       ('fractional_reference', cases['fractional_reference'])):
        performance = summarize(case.result, fx_rate=split_fx, fx_history=fx_history,
                                operations_monthly_krw=None)
        key: dict[str, JsonValue] = {'split': split.name, 'benchmark': name, 'cost_scenario': scenario}
        tables['benchmarks'].append({**key, **asdict(performance.summary),
                **asdict(additional_summary(case.result, performance, split)),
                'status': case.status, 'included_symbols': ','.join(case.included_symbols),
                'missing_symbols': ','.join(case.missing_symbols), 'notes': ';'.join(case.notes),
                'starting_usd': case.result.starting_cash,
                'estimated_liquidation_value_usd': case.estimated_liquidation_value_usd,
                'full_basket_available': case.feasibility.full_basket_available,
                'full_basket_required_initial_cash_usd': case.feasibility.full_basket_required_initial_cash_usd,
                'full_basket_one_share_outlay_usd': case.feasibility.full_basket_one_share_outlay_usd,
            })
        tables['benchmark_monthly'].extend(key | row for row in monthly_rows(performance, split))
        for table, rows in (('benchmark_equity', case.result.equity_curve),
                            ('benchmark_fills', case.result.trades),
                            ('benchmark_feasibility', case.feasibility.symbols)):
            tables[table].extend(key | asdict(row) for row in rows)


def count_submitted_buys(orders: list[AcceptedOrder], rejections: tuple[BacktestRejection, ...]) -> int:
    """Only immediate buy submission rejections reduce the risk-approved count."""
    identities = {(order.symbol, order.timestamp) for order in orders}
    immediate = sum(row.timestamp == row.signal_timestamp
                    and row.reason != "end_of_data_unfilled"
                    and (row.symbol, row.signal_timestamp) in identities for row in rejections)
    return len(orders) - immediate
