from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_entry_policy_comparison.py"


def test_entry_comparison_smoke_uses_identical_risk_and_three_policies(
    tmp_path: Path,
) -> None:
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
            "synthetic assumption",
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
    assert len(rows) == 18
    assert {row["policy"] for row in rows} == {"A", "B", "C"}
    assert {row["common_risk_pct"] for row in rows} == {"0.01"}
    assert all(row["literal_five_minute_exits"] == "" for row in rows)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["order_api_calls"] == 0
    assert manifest["assessment"] == "SYNTHETIC_SMOKE_ONLY"


def test_entry_comparison_import_blocks_network_without_application_modules() -> None:
    driver = """import runpy, sys, socket, subprocess
runpy.run_path("scripts/run_entry_policy_comparison.py", run_name="offline_test")
assert not any(name.startswith(("nasdaq_auto_trader.engine", "nasdaq_auto_trader.config", "nasdaq_auto_trader.kis")) for name in sys.modules)
for attempt in (socket.socket, lambda: subprocess.Popen([sys.executable, "-V"])):
    try:
        attempt()
    except RuntimeError as error:
        assert "forbidden" in str(error)
    else:
        raise AssertionError("network/subprocess access allowed")
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


def test_nonempty_output_without_protocol_cannot_be_overwritten(tmp_path: Path) -> None:
    sentinel = tmp_path / "summary.csv"
    sentinel.write_text("preserve existing work")
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
            "test",
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
    assert sentinel.read_text() == "preserve existing work"
    assert not (tmp_path / "protocol.json").exists()
