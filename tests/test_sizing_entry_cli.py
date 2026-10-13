import csv
import json
from pathlib import Path

from tests.test_profitability_cli import ROOT, run_cli

PROFILE = ROOT / 'experiments/sizing_entry_80000/profile.json'


def test_existing_cli_runs_only_three_profiles_with_same_commissions(tmp_path: Path) -> None:
    # Given the separately frozen three-profile experiment.
    # When the existing CLI drives synthetic plumbing, not historical evidence.
    completed = run_cli(tmp_path, PROFILE)
    # Then each synthetic split has exactly three profiles and two allowed costs.
    assert completed.returncode == 0, completed.stderr
    with (tmp_path / 'summary.csv').open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 18
    assert {row['profile'] for row in rows} == {'P0', 'P1', 'P2'}
    assert {row['cost_scenario'] for row in rows} == {'base', 'high_impact'}
    assert {row['risk_pct'] for row in rows} == {'0.02'}
    protocol = json.loads((tmp_path / 'protocol.json').read_text())
    assert {row['commission_pct'] for row in protocol['costs']} == {.0025}
    assert {row['minimum_commission'] for row in protocol['costs']} == {0}
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    assert manifest['assessment'] == 'SYNTHETIC_SMOKE_ONLY'
    assert manifest['order_api_calls'] == manifest['cancel_api_calls'] == 0
    assert (tmp_path / 'sizing.csv').is_file()
    assert (tmp_path / 'breakout.csv').is_file()


def test_three_profile_drift_is_rejected(tmp_path: Path) -> None:
    # Given an unauthorized change to the frozen stop distance.
    data = json.loads(PROFILE.read_text())
    data['exit']['initial_stop_pct'] = .10
    profile = tmp_path / 'changed.json'
    profile.write_text(json.dumps(data))
    # When submitted through the same CLI option.
    completed = run_cli(tmp_path / 'out', profile)
    # Then no performance table is created.
    assert completed.returncode != 0
    assert 'frozen' in completed.stderr
    assert not (tmp_path / 'out/summary.csv').exists()
