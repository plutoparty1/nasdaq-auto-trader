# /// script
# requires-python = ">=3.11"
# dependencies = ["pytest"]
# ///
# How to run: python scripts/run_offline_tests.py -q docs/early-exit-audit-20260929/qa-review/test_cli_review.py
"""TEST ONLY: independently exercise the actual offline command boundary."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
QA = Path(__file__).parent
CLI = ROOT / "scripts/run_exit_experiments.py"


def run_cli(output: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(CLI), "--output", str(output), "--usdkrw", "1400", "--fx-source", "TEST ONLY QA assumption", "--fx-as-of", "2020-01-01", *extra]
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    with (QA / "cli-observations.txt").open("a", encoding="utf-8") as handle:
        handle.write(f"COMMAND {args!r}\nEXIT {result.returncode}\n{result.stdout}{result.stderr}\n")
    return result


@pytest.mark.parametrize("flag,value,expected", [
    ("--usdkrw", "0", "positive finite"),
    ("--usdkrw", "-1", "positive finite"),
    ("--usdkrw", "nan", "positive finite"),
    ("--usdkrw", "inf", "positive finite"),
    ("--monthly-operations-krw", "-1", "nonnegative"),
    ("--monthly-operations-krw", "nan", "nonnegative"),
    ("--monthly-operations-krw", "inf", "nonnegative"),
    ("--train-end", "2020-09-30", "increase strictly"),
    ("--validation-end", "2020-01-01", "increase strictly"),
    ("--fx-as-of", "not-a-date", "Invalid isoformat"),
])
def test_invalid_cli_numbers_and_dates(tmp_path: Path, flag: str, value: str, expected: str) -> None:
    # Given an invalid input at the actual command boundary.
    # When the offline CLI is invoked.
    result = run_cli(tmp_path, "--synthetic-smoke", flag, value)
    # Then it exits without a successful result manifest.
    assert result.returncode != 0 and expected in result.stderr
    assert not (tmp_path / "manifest.json").exists()


@pytest.mark.parametrize("field,value", [("dry_run", False), ("dry_run", "true"), ("broker", "kis"), ("starting_krw", 79999), ("max_position_pct", 50)])
def test_invalid_offline_settings(tmp_path: Path, field: str, value: str | int | bool) -> None:
    # Given a settings file outside the allowed experiment contract.
    settings = json.loads((ROOT / "experiments/early_exit/settings.json").read_text())
    settings[field] = value
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    # When an experiment is requested.
    result = run_cli(tmp_path / "out", "--synthetic-smoke", "--settings", str(path))
    # Then it fails closed and cannot report success.
    assert result.returncode != 0
    assert not (tmp_path / "out/manifest.json").exists()


def test_missing_history_inputs(tmp_path: Path) -> None:
    # Given no historical bars or provenance.
    # When historical execution is requested.
    result = run_cli(tmp_path)
    # Then all required historical inputs are named.
    assert result.returncode != 0 and "historical runs require" in result.stderr


def test_frozen_output_is_immutable() -> None:
    # Given a completed synthetic comparison.
    path = QA / "smoke-base"
    before = (path / "protocol.json").read_bytes()
    # When the same output is requested again.
    result = run_cli(path, "--synthetic-smoke")
    # Then the frozen protocol and artifacts cannot be replaced.
    assert result.returncode != 0 and "frozen protocol" in result.stderr
    assert (path / "protocol.json").read_bytes() == before


@pytest.mark.parametrize("rows,expected", [
    ([("2020-01-01Z", "1400"), ("2020-01-01Z", "1500")], "unique"),
    ([("2020-01-01T00:00:00+00:00", "1400"), ("2020-01-01T09:00:00+09:00", "1500")], "unique"),
    ([("2020-01-02", "1400")], "at or before"),
    ([("2020-01-01", "0")], "finite and positive"),
    ([], "nonempty"),
])
def test_fx_history_failures(tmp_path: Path, rows: list[tuple[str, str]], expected: str) -> None:
    # Given malformed or insufficiently early FX observations.
    path = tmp_path / "fx.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "usdkrw"])
        writer.writerows(rows)
    # When the complete CLI is run.
    result = run_cli(tmp_path / "out", "--synthetic-smoke", "--fx-history", str(path))
    # Then invalid FX never reaches a valid manifest.
    assert result.returncode != 0 and expected in result.stderr
    assert not (tmp_path / "out/manifest.json").exists()


def test_blank_fx_provenance_rejected(tmp_path: Path) -> None:
    # Given whitespace that provides no FX provenance.
    # When the actual CLI receives it.
    result = run_cli(tmp_path, "--synthetic-smoke", "--fx-source", "   ")
    # Then mandatory source information cannot be bypassed.
    assert result.returncode != 0


def write_flat_fixture(path: Path, count: int) -> tuple[Path, Path]:
    bars = path / "TEST-ONLY-flat.csv"
    provenance = path / "TEST-ONLY-provenance.json"
    with bars.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["symbol", "timestamp", "open", "high", "low", "close", "volume"])
        for i in range(count):
            stamp = (datetime(2020, 1, 1, 21, tzinfo=timezone.utc) + timedelta(days=i)).isoformat()
            writer.writerow(["TEST_ONLY", stamp, 1000, 1000, 1000, 1000, 1000])
    provenance.write_text(json.dumps({"data_source": "TEST ONLY synthetic flat", "bar_interval": "1Day", "universe_source": "TEST ONLY singleton", "universe_as_of": "2019-12-31", "survivorship_corrected": False, "synthetic": True, "adjustment_policy": "TEST ONLY unadjusted"}), encoding="utf-8")
    return bars, provenance


@pytest.mark.parametrize("count", [0, 9])
def test_insufficient_bars(tmp_path: Path, count: int) -> None:
    # Given empty or fewer than ten dated bars.
    bars, provenance = write_flat_fixture(tmp_path, count)
    # When explicit historical-path inputs are submitted.
    result = run_cli(tmp_path / "out", "--bars", str(bars), "--provenance", str(provenance), "--train-end", "2020-01-04", "--validation-end", "2020-01-06")
    # Then no result manifest exists.
    assert result.returncode != 0 and ("at least one bar" if count == 0 else "ten timestamps") in result.stderr
    assert not (tmp_path / "out/manifest.json").exists()


def test_no_trade_fx_operations_cli(tmp_path: Path) -> None:
    # Given flat unaffordable TEST ONLY prices and known TEST ONLY FX moves.
    output = tmp_path / "no-trade-fx"
    fixture_dir = tmp_path / "flat-fixtures"
    fixture_dir.mkdir(exist_ok=True)
    bars, provenance = write_flat_fixture(fixture_dir, 100)
    fx = fixture_dir / "TEST-ONLY-fx.csv"
    fx.write_text("timestamp,usdkrw\n2020-01-01,1000\n2020-02-01,1100\n2020-03-01,900\n", encoding="utf-8")
    # When known monthly operating costs are explicitly charged.
    result = run_cli(output, "--bars", str(bars), "--provenance", str(provenance), "--train-end", "2020-02-10", "--validation-end", "2020-03-10", "--fx-history", str(fx), "--monthly-operations-krw", "1000")
    # Then zero stock return is unsupported; FX/cost movements remain visible.
    assert result.returncode == 0, result.stderr
    with (output / "summary.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 120
    assert all(row["evidence_status"] == "no_executions" for row in rows)
    assert all(float(row["cumulative_return_pct"]) == 0 for row in rows)
    assert all(row["fx_mode"] == "historical_fx" for row in rows)
    assert all(float(row["after_operations_return_pct"]) < float(row["cumulative_krw_return_pct"]) for row in rows)



def test_missing_required_fx_arguments(tmp_path: Path) -> None:
    # Given no explicit FX source, rate, or date.
    # When the actual entry point is requested.
    result = subprocess.run([sys.executable, str(CLI), "--synthetic-smoke", "--output", str(tmp_path)], cwd=ROOT, capture_output=True, text=True, timeout=20, check=False)
    # Then argparse identifies each mandatory provenance argument.
    assert result.returncode == 2
    assert all(flag in result.stderr for flag in ("--usdkrw", "--fx-source", "--fx-as-of"))
