from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/run_entry_policy_comparison.py'
PROFILE = ROOT / 'experiments/profitability_80000/profile.json'


def run_cli(output: Path, profile: Path = PROFILE) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), '--synthetic-smoke', '--output', str(output),
         '--usdkrw', '1400', '--fx-source', 'synthetic-test-only', '--fx-as-of', '2020-01-01',
         '--profitability-profile', str(profile)],
        cwd=ROOT, capture_output=True, text=True, timeout=90, check=False,
    )


def test_frozen_twelve_profiles_execute_with_cash_and_integer_benchmarks(tmp_path: Path) -> None:
    # Given: a separate output and the frozen offline-only profile.
    # When: the existing isolated CLI evaluates its synthetic plumbing fixture.
    completed = run_cli(tmp_path)
    # Then: exactly twelve profiles and two costs per split; no live integration.
    assert completed.returncode == 0, completed.stderr
    with (tmp_path / 'summary.csv').open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 72
    assert len({row['profile'] for row in rows}) == 12
    assert {row['risk_pct'] for row in rows} == {'0.01', '0.02', '0.04'}
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    assert manifest['assessment'] == 'SYNTHETIC_SMOKE_ONLY'
    assert manifest['order_api_calls'] == manifest['cancel_api_calls'] == 0
    with (tmp_path / 'benchmarks.csv').open() as handle:
        benchmarks = list(csv.DictReader(handle))
    assert {row['benchmark'] for row in benchmarks} == {'usd_cash', 'integer_buy_hold', 'fractional_reference'}


def test_modified_profile_rejected_before_results(tmp_path: Path) -> None:
    # Given: a drifted budget outside the twelve prespecified profiles.
    raw = json.loads(PROFILE.read_text())
    raw['risk_budgets'] = [.01, .02, .05]
    profile = tmp_path / 'changed.json'
    profile.write_text(json.dumps(raw))
    # When: the frozen experiment receives that input.
    completed = run_cli(tmp_path / 'output', profile)
    # Then: the experiment fails before a results table exists.
    assert completed.returncode != 0
    assert 'frozen' in completed.stderr
    assert not (tmp_path / 'output/summary.csv').exists()


def test_existing_results_are_preserved(tmp_path: Path) -> None:
    # Given: an output containing user-owned results.
    target = tmp_path / 'summary.csv'
    target.write_text('preserve')
    # When: an experiment targets that directory.
    completed = run_cli(tmp_path)
    # Then: it cannot overwrite any prior result.
    assert completed.returncode != 0
    assert target.read_text() == 'preserve'
