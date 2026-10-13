from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_exit_experiments.py"


def test_cli_smoke_emits_complete_matrix_without_live_config(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--synthetic-smoke",
            "--output",
            str(tmp_path),
            "--usdkrw",
            "1400",
            "--fx-source",
            "test-assumption",
            "--fx-as-of",
            "2020-01-01",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    with (tmp_path / "summary.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 120
    assert {row["split"] for row in rows} == {"train", "validation", "final"}
    assert any(int(row["completed_roundtrips"]) > 0 for row in rows)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["assessment"] == "SYNTHETIC_SMOKE_ONLY"


def test_network_socket_is_denied_and_live_modules_are_not_loaded() -> None:
    driver = """import runpy, sys, socket
runpy.run_path("scripts/run_exit_experiments.py", run_name="offline_test")
assert "nasdaq_auto_trader.config" not in sys.modules
assert "nasdaq_auto_trader.engine" not in sys.modules
try:
    socket.socket()
except RuntimeError as error:
    assert "forbidden" in str(error)
else:
    raise AssertionError("socket was not denied")
print("isolated")
"""
    result = subprocess.run(
        [sys.executable, "-c", driver],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "isolated"


def test_cli_rejects_blank_fx_provenance_before_any_run(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--synthetic-smoke",
            "--output",
            str(tmp_path),
            "--usdkrw",
            "1400",
            "--fx-source",
            "   ",
            "--fx-as-of",
            "2020-01-01",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode != 0
    assert not (tmp_path / "protocol.json").exists()


def test_daily_runner_rejects_intraday_bars_with_daily_label() -> None:
    import pytest

    from nasdaq_auto_trader.exit_experiment import validate_daily_bars
    from nasdaq_auto_trader.models import Bar

    bars = {
        "TEST": [
            Bar("TEST", "2025-01-02T14:30:00+00:00", 10, 10, 10, 10, 100),
            Bar("TEST", "2025-01-02T14:35:00+00:00", 10, 10, 10, 10, 100),
        ]
    }
    with pytest.raises(ValueError, match="daily|1Day"):
        validate_daily_bars(bars)
