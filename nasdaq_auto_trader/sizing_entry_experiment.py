"""Three frozen profiles, sharing the established offline execution and metrics."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from typing import Literal, assert_never

from .backtest import Backtester
from .entry_comparison import JsonValue, _write_rows
from .entry_comparison_metrics import monthly_rows
from .exit_experiment import EvaluationSplit, validate_daily_bars
from .exit_experiment_config import CostScenario, ExperimentInputError
from .exit_experiment_metrics import FxPoint, fx_at, summarize
from .models import Bar
from .profitability_execution import ConservativeCosts
from .profitability_experiment import (
    ProfitabilityEvaluation,
    _benchmarks,
    count_submitted_buys,
)
from .profitability_metrics import additional_summary
from .profitability_risk import ProfitabilityRisk
from .profitability_strategy import ProfitabilityStrategy
from .sizing_entry_config import SIZING_PROFILE_SHA, frozen_sizing_setup
from .sizing_entry_execution import DynamicExecutionBook
from .sizing_entry_risk import DynamicEntryRisk
from .sizing_entry_strategy import BreakoutEntryStrategy
from .strategy_config import StrategyConfig


def run_sizing_entry_suite(
    config: StrategyConfig, bars: dict[str, list[Bar]], splits: tuple[EvaluationSplit, ...],
    output: Path, costs: tuple[CostScenario, ...], *, fx_rate: float,
    manifest: dict[str, JsonValue], profile_path: Path,
    fx_history: tuple[FxPoint, ...] = (), operations_monthly_krw: float | None = None,
) -> None:
    del costs
    setup = frozen_sizing_setup(profile_path, manifest, splits)
    validate_daily_bars(bars)
    if operations_monthly_krw is not None:
        raise ExperimentInputError('unverified operations costs remain unknown in frozen comparison')
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ExperimentInputError('output must be empty; archived results are preserved')
    manifest = dict(manifest)
    if manifest.get('assessment') != 'SYNTHETIC_SMOKE_ONLY':
        manifest['assessment'] = 'EXPLORATORY_ALREADY_USED_DATA'
    manifest['sizing_entry_profile_sha256'] = SIZING_PROFILE_SHA
    manifest['no_independent_holdout'] = True
    manifest['limitations'] = [
        'Three profiles only: P0 fixed one, P1 dynamic integer, P2 replacement daily breakout entry',
        'All retain fixed_8 exits, 2% trade risk and frozen common caps; no averaging down',
        'Both costs use the same unverified commission/minimum; high_impact widens only spread/slippage',
        'Prior USD0.10 minimum stress preserved separately; actual fees/levies/FX/operations unknown',
        'Previously used hindsight cohort; exploratory, not independent validation',
        'Close-only protective observation; next admissible open simulation cannot prove queue execution',
        'Price-only dividends omitted; unrealized equity included; passive hold retains original one-share rule',
    ]
    protocol = {'frozen_profile': json.loads(profile_path.read_text(encoding='utf-8')),
                'strategy': asdict(config), 'exit': asdict(setup.policy),
                'costs': [asdict(cost) for cost in setup.costs],
                'splits': [asdict(split) for split in splits], 'manifest': manifest}
    protocol['sha256'] = hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()
    (output / 'protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    names = ('summary', 'monthly', 'fills', 'reasons', 'equity', 'constraints', 'orders',
             'order_rejections', 'decisions', 'blockers', 'sizing', 'breakout', 'benchmarks',
             'benchmark_monthly', 'benchmark_equity', 'benchmark_fills', 'benchmark_feasibility')
    tables: dict[str, list[dict[str, JsonValue]]] = {name: [] for name in names}
    profiles: tuple[Literal['P0', 'P1', 'P2'], ...] = ('P0', 'P1', 'P2')
    for split in splits:
        prefix = {symbol: [bar for bar in history if bar.timestamp <= split.end]
                  for symbol, history in bars.items()}
        rate = fx_at(split.start, fx_rate, fx_history)
        fx_stamp = next((point.timestamp for point in reversed(fx_history)
                         if point.timestamp <= split.start), str(manifest.get('fx_as_of', '')))
        for scenario in setup.costs:
            cost = ConservativeCosts(scenario.commission_pct, scenario.minimum_commission,
                                     scenario.spread_bps, scenario.slippage_bps, 1)
            _benchmarks(prefix, split, cost, rate, fx_history, scenario.name, tables)
            for profile in profiles:
                breakout: BreakoutEntryStrategy | None = None
                dynamic: DynamicEntryRisk | None = None
                match profile:
                    case 'P0':
                        strategy = ProfitabilityStrategy(config, setup.policy)
                        risk = ProfitabilityRisk(strategy, cost, .02)
                    case 'P1':
                        strategy = ProfitabilityStrategy(config, setup.policy)
                        dynamic = DynamicEntryRisk(strategy, cost)
                        risk = dynamic
                    case 'P2':
                        breakout = BreakoutEntryStrategy(config, setup.policy)
                        strategy = breakout
                        dynamic = DynamicEntryRisk(strategy, cost)
                        risk = dynamic
                    case unreachable:
                        assert_never(unreachable)
                adapter = ProfitabilityEvaluation(strategy, risk, split, cost)
                engine = Backtester(adapter, risk, costs=cost, max_trade_risk_pct=.02,
                                    max_portfolio_risk_pct=.06, max_total_position_pct=.5,
                                    fill_observer=strategy, risk_includes_costs=True)
                if dynamic is not None:
                    engine.execution_book_type = DynamicExecutionBook
                    engine.on_book_created = dynamic.bind_book
                result = engine.run(prefix, starting_cash=80000 / rate)
                result = replace(result, equity_curve=tuple(
                    point for point in result.equity_curve if point.timestamp >= split.start))
                performance = summarize(result, fx_rate=rate, fx_history=fx_history,
                                        operations_monthly_krw=None)
                records = [row for row in risk.records if row.timestamp >= split.start]
                key: dict[str, JsonValue] = {'split': split.name, 'profile': profile,
                    'policy': 'fixed_8', 'risk_pct': .02, 'cost_scenario': scenario.name}
                tables['summary'].append({**key, **asdict(performance.summary),
                    **asdict(additional_summary(result, performance, split)),
                    'starting_krw': 80000, 'starting_usd': result.starting_cash,
                    'initial_usdkrw': rate, 'fx_as_of': fx_stamp,
                    'gross_return_before_model_costs_pct':
                        100 * (result.ending_value - result.starting_cash + performance.summary.trading_cost_usd) / result.starting_cash,
                    'order_candidates': len(risk.accepted_orders),
                    'submitted_buy_orders': count_submitted_buys(risk.accepted_orders, result.rejections),
                    'risk_budget_blocked_signals': sum(row.entry_condition_met and
                        'trade_risk_budget' in row.blocking_conditions for row in records),
                    'max_filled_buy_qty': max((row.qty for row in result.trades if row.side == 'buy'), default=0),
                    'assessment': manifest['assessment']})
                tables['monthly'].extend(key | row for row in monthly_rows(performance, split))
                for name, entries in (('fills', result.trades), ('reasons', performance.reasons),
                    ('equity', result.equity_curve), ('constraints', records), ('orders', risk.accepted_orders),
                    ('order_rejections', result.rejections), ('decisions', strategy.records)):
                    tables[name].extend(key | asdict(row) for row in entries)
                if dynamic is not None:
                    tables['sizing'].extend(key | asdict(row) for row in dynamic.sizing_records)
                if breakout is not None:
                    tables['breakout'].extend(key | asdict(row) for row in breakout.breakout_records)
                first = Counter(row.first_reason for row in records)
                conditions = Counter(reason for row in records for reason in row.blocking_conditions)
                for reason in sorted(first.keys() | conditions.keys()):
                    tables['blockers'].append(key | {'reason': reason, 'first_count': first[reason],
                                                     'all_condition_count': conditions[reason]})
    for name, rows in tables.items():
        _write_rows(output / f'{name}.csv', rows)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
