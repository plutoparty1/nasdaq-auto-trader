"""Frozen identity for the three-profile offline sizing/entry comparison."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .entry_comparison import JsonValue
from .exit_experiment import EvaluationSplit
from .exit_experiment_config import CostScenario, ExperimentInputError
from .experimental_exit_models import ExitPolicy
from .profitability_config import frozen_candidates

SIZING_PROFILE_SHA: Final = '68c2ba260005c550c3fe88e09e734812476df031472a43b68c65e31c057f0fc9'


@dataclass(frozen=True, slots=True)
class SizingSetup:
    policy: ExitPolicy
    costs: tuple[CostScenario, ...]


def frozen_sizing_setup(
    profile_path: Path, manifest: dict[str, JsonValue], splits: tuple[EvaluationSplit, ...],
) -> SizingSetup:
    if hashlib.sha256(profile_path.read_bytes()).hexdigest() != SIZING_PROFILE_SHA:
        raise ExperimentInputError('sizing entry profile differs from frozen three-profile protocol')
    raw = json.loads(profile_path.read_text(encoding='utf-8'))
    root = Path(__file__).resolve().parents[1]
    original = root / 'experiments/profitability_80000/profile.json'
    fixed = next(candidate for candidate in frozen_candidates(original, manifest) if candidate.name == 'fixed_8')
    if fixed.policy is None:
        raise ExperimentInputError('fixed_8 exit policy is unavailable')
    if manifest.get('profile_sha256') != raw['source_sha256']['experiments/entry_policy/profile.json']:
        raise ExperimentInputError('entry settings differ from the frozen baseline')
    if manifest.get('assessment') != 'SYNTHETIC_SMOKE_ONLY':
        if manifest.get('bars_sha256') != raw['data_sha256'][raw['data_file']]:
            raise ExperimentInputError('only the frozen main historical dataset is permitted')
        if manifest.get('symbols') != raw['symbols']:
            raise ExperimentInputError('all three frozen cohort symbols are required')
        if len(splits) != 1 or splits[0].start != raw['evaluation_start'] or splits[0].end != raw['evaluation_end']:
            raise ExperimentInputError('evaluation window differs from frozen main comparison')
    costs = tuple(CostScenario(**row) for row in raw['costs'])
    return SizingSetup(fixed.policy, costs)
