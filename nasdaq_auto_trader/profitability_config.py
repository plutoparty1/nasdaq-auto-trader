"""Immutable experimental identity; live configuration is never imported."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

from .entry_comparison import JsonValue
from .exit_experiment import Candidate, candidates
from .exit_experiment_config import ExperimentInputError

FROZEN_PROFILE_SHA: Final = '69e6addc681961af86e2d08ca3f2188aa67ed5fe37dacefa234d86f31eff20a1'
RISK_BUDGETS: Final = (0.01, 0.02, 0.04)


def frozen_candidates(profile_path: Path, manifest: dict[str, JsonValue]) -> tuple[Candidate, ...]:
    """Reject experimental drift before any performance output is calculated."""
    if hashlib.sha256(profile_path.read_bytes()).hexdigest() != FROZEN_PROFILE_SHA:
        raise ExperimentInputError('profitability profile differs from the frozen twelve-profile protocol')
    raw = json.loads(profile_path.read_text(encoding='utf-8'))
    root = Path(__file__).resolve().parents[1]
    for relative, expected in raw['source_sha256'].items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ExperimentInputError(f'frozen source changed: {relative}')
    if manifest.get('assessment') != 'SYNTHETIC_SMOKE_ONLY':
        allowed = {raw['data_sha256'][name] for name in
                   ('actual_trade_group.csv', 'actual_trade_group_after_corporate_action.csv')}
        if manifest.get('bars_sha256') not in allowed:
            raise ExperimentInputError('historical bars must match a frozen cohort hash')
        if manifest.get('fx_history_sha256') != raw['data_sha256']['usdkrw.csv']:
            raise ExperimentInputError('historical FX must match the frozen reference history')
    return (Candidate('C', False, None), *candidates()[2:])
