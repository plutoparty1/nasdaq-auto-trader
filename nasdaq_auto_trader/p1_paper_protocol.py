"""Frozen P1 identity and bounded, credential-free validation inputs."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from .entry_comparison import JsonValue, load_entry_profile
from .exit_experiment import candidates
from .exit_experiment_config import ExperimentInputError
from .experimental_exit_models import ExitPolicy
from .p1_paper_codec import read_json
from .profitability_execution import ConservativeCosts
from .profitability_strategy import ProfitabilityStrategy
from .sizing_entry_config import SIZING_PROFILE_SHA
from .sizing_entry_risk import DynamicEntryRisk
from .strategy_config import StrategyConfig

SYMBOLS: Final = ('CMCSA', 'HIVE', 'KDP')
STARTING_USD: Final = 54.072814354631596


def mapping(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ExperimentInputError('paper_object_required')
    return value


def text_field(value: JsonValue) -> str:
    if not isinstance(value, str) or not value:
        raise ExperimentInputError('paper_text_required')
    return value


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ExperimentInputError('paper_timestamp_timezone_required')
    return parsed.astimezone(UTC)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class PaperSession:
    day: str
    open_at: str
    close_at: str


@dataclass(frozen=True, slots=True)
class PaperProtocol:
    path: Path
    sha256: str
    frozen_at: str
    config: StrategyConfig
    policy: ExitPolicy
    sessions: tuple[PaperSession, ...]
    costs: dict[str, ConservativeCosts]
    raw: dict[str, JsonValue]


def effective_settings(config: StrategyConfig, policy: ExitPolicy,
                       costs: dict[str, ConservativeCosts]) -> dict[str, JsonValue]:
    risk = DynamicEntryRisk(ProfitabilityStrategy(config, policy), costs['base'])
    return {'strategy_config': asdict(config), 'exit_policy': asdict(policy),
            'risk_config': asdict(risk.config), 'symbols': list(SYMBOLS),
            'costs': {name: asdict(cost) for name, cost in costs.items()},
            'signal_timeframe': '1Day', 'protection_timeframe': 'completed_daily_close',
            'warmup_bars': 64, 'max_total_position_pct': .5,
            'portfolio_risk_pct': .06, 'daily_loss_halt_pct': .02,
            'quantity_policy': 'maximum_feasible_integer',
            'observation_sessions': 60, 'minimum_completed_trades_per_cost': 10,
            'candidate_rule': 'both_costs_positive_usd_and_above_cash_and_executable_hold',
            'insufficient_rule': 'few_trades_or_data_fault_or_missing_terminal_or_unknown_fx',
            'fx_max_age_days': 7, 'cash_interest_pct': 0}


def load_protocol(path: Path) -> PaperProtocol:
    """Source/calendar drift requires a new version, never an amended live checkpoint."""
    raw = read_json(path.read_text(encoding='utf-8'))
    data = mapping(raw)
    if data.get('version') != 'p1-paper-v1' or data.get('profile') != 'P1':
        raise ExperimentInputError('paper_protocol_version_invalid')
    root = Path(__file__).resolve().parents[1]
    sources = mapping(data.get('source_sha256'))
    if not {'nasdaq_auto_trader/p1_paper_protocol.py',
            'experiments/sizing_entry_80000/profile.json'} <= sources.keys():
        raise ExperimentInputError('paper_source_identity_incomplete')
    for name, expected in sources.items():
        source = (root / name).resolve()
        if not source.is_relative_to(root) or digest(source) != expected:
            raise ExperimentInputError('paper_source_drift_requires_new_version:' + name)
    calendar = path.parent / 'sessions.csv'
    if digest(calendar) != data.get('calendar_sha256'):
        raise ExperimentInputError('paper_calendar_drift_requires_new_version')
    with calendar.open(encoding='utf-8', newline='') as handle:
        sessions = tuple(PaperSession(row['session_date'], row['open_at'], row['close_at'])
                         for row in csv.DictReader(handle))
    if not sessions or any(utc(s.open_at) >= utc(s.close_at) for s in sessions):
        raise ExperimentInputError('paper_calendar_invalid')
    if tuple(s.day for s in sessions) != tuple(sorted({s.day for s in sessions})):
        raise ExperimentInputError('paper_calendar_not_unique_sorted')
    config = load_entry_profile(root / 'experiments/entry_policy/profile.json')
    policy = next(item.policy for item in candidates() if item.name == 'fixed_8')
    if policy is None:
        raise ExperimentInputError('paper_fixed8_unavailable')
    frozen_at = text_field(data.get('frozen_at'))
    _ = utc(frozen_at)
    if data.get('starting_usd') != STARTING_USD:
        raise ExperimentInputError('paper_initial_usd_drift')
    costs = {'base': ConservativeCosts(.0025, 0, 10, 10, 1),
             'high_impact': ConservativeCosts(.0025, 0, 30, 30, 1)}
    if digest(root / 'experiments/sizing_entry_80000/profile.json') != SIZING_PROFILE_SHA:
        raise ExperimentInputError('paper_original_p1_profile_drift')
    settings = effective_settings(config, policy, costs)
    settings_sha = hashlib.sha256(json.dumps(settings, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if data.get('effective_settings_sha256') != settings_sha:
        raise ExperimentInputError('paper_effective_settings_hash_invalid')
    if data.get('effective_settings') != settings:
        raise ExperimentInputError('paper_effective_settings_drift')
    if data.get('source_archive') != 'source-snapshot.zip' or digest(path.parent / 'source-snapshot.zip') != data.get('source_archive_sha256'):
        raise ExperimentInputError('paper_source_archive_hash_invalid')
    return PaperProtocol(path, digest(path), frozen_at, config, policy, sessions, costs, data)
