# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python docs/entry-policy-audit-20260929/qa/check_cli.py
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Final

QA: Final = Path(__file__).resolve().parent
ROOT: Final = QA.parents[2]
PUBLIC: Final = Path(os.environ["LOCALAPPDATA"]) / "NasdaqAutoTrader/research/entry-policy-20260929/public"
SCRIPT: Final = ROOT / "scripts/run_entry_policy_comparison.py"


def main() -> None:
    cases = QA / (sys.argv[1] if len(sys.argv) > 1 else "cli-cases")
    cases.mkdir(exist_ok=True)
    results = []

    def reject(name: str, args: list[str], expected: str) -> None:
        output = cases / name
        command = [sys.executable, str(SCRIPT), "--output", str(output), "--usdkrw", "1400", "--fx-source", "QA", "--fx-as-of", "2020-01-01", *args]
        response = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=45, check=False)
        (cases / f"{name}.txt").write_text(response.stdout + response.stderr, encoding="utf-8")
        passed = response.returncode != 0 and expected.lower() in response.stderr.lower()
        results.append({"case": name, "exit": response.returncode, "pass": passed, "expected_error": expected, "summary_created": (output / "summary.csv").exists()})

    smoke = QA / "cli-smoke"
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in smoke.iterdir() if path.is_file()}
    reject("reuse-frozen-output", ["--synthetic-smoke", "--output", str(smoke)], "output")
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in smoke.iterdir() if path.is_file()}
    assert before == after
    for label, value in (("zero", "0"), ("negative", "-1"), ("nan", "nan"), ("infinity", "inf")):
        reject(f"fx-{label}", ["--synthetic-smoke", "--usdkrw", value], "positive USD/KRW")
    for label, value in (("negative", "-1"), ("nan", "nan"), ("infinity", "inf")):
        reject(f"operations-{label}", ["--synthetic-smoke", "--monthly-operations-krw", value], "operations cost")
    reject("missing-historical-arguments", [], "historical runs need")
    provenance = {"data_source": "QA public copy", "bar_interval": "1Day", "adjustment_policy": "public quote", "universe_source": "SPY control", "collected_at": "2026-09-29T12:37:02+00:00"}
    provenance_path = cases / "provenance.json"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    historical = ["--bars", str(PUBLIC / "SPY.csv"), "--provenance", str(provenance_path), "--train-end", "2025-08-29", "--validation-end", "2026-02-27", "--control"]
    wrong = cases / "wrong-interval.json"
    wrong.write_text(json.dumps(provenance | {"bar_interval": "5Min"}), encoding="utf-8")
    reject("wrong-bar-interval", [*historical, "--provenance", str(wrong)], "1Day signal bars")
    reject("missing-case-cohort", historical[:-1], "every symbol")
    with (PUBLIC / "SPY.csv").open(encoding="utf-8-sig", newline="") as handle:
        source = list(csv.DictReader(handle))
    for label, mutation, expected in (("nan-high", {"high": "nan"}, "finite"), ("negative-low", {"low": "-1"}, "greater than zero"), ("invalid-ohlc", {"high": "0.1"}, "high must be"), ("date-only", {"timestamp": source[80]["timestamp"][:10]}, "timestamp")):
        data = [dict(row) for row in source]
        data[80].update(mutation)
        path = cases / f"{label}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(source[0]))
            writer.writeheader()
            writer.writerows(data)
        reject(label, [*historical, "--bars", str(path)], expected)
    for label, data, expected in (("duplicate-bar", source + [source[-1]], "duplicate"), ("short-history", source[:79], "80 daily")):
        path = cases / f"{label}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(source[0]))
            writer.writeheader()
            writer.writerows(data)
        reject(label, [*historical, "--bars", str(path)], expected)
    profile = json.loads((ROOT / "experiments/entry_policy/profile.json").read_text(encoding="utf-8"))
    profile["risk"]["risk_per_trade_pct"] = .05
    profile_path = cases / "changed-risk.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    reject("changed-risk", ["--synthetic-smoke", "--profile", str(profile_path)], "prespecified")
    for label, section, key, value, expected in (("changed-exit", "strategy", "stop_loss_pct", .08, "exit parameters"), ("changed-capital", "limits", "starting_krw", 100000, "remain frozen")):
        changed = json.loads((ROOT / "experiments/entry_policy/profile.json").read_text(encoding="utf-8"))
        changed[section][key] = value
        path = cases / f"{label}.json"
        path.write_text(json.dumps(changed), encoding="utf-8")
        reject(label, ["--synthetic-smoke", "--profile", str(path)], expected)
    profile = json.loads((ROOT / "experiments/entry_policy/profile.json").read_text(encoding="utf-8"))
    profile["policies"] = ["B", "C"]
    path = cases / "changed-policies.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    reject("changed-policies", ["--synthetic-smoke", "--profile", str(path)], "frozen A/B/C")
    for label, contents, expected in (("duplicate-fx", "timestamp,usdkrw\n2020-01-01,1400\n2020-01-01,1400\n", "unique timestamps"), ("late-fx", "timestamp,usdkrw\n2030-01-01,1400\n", "before the first evaluation"), ("nan-fx-history", "timestamp,usdkrw\n2020-01-01,nan\n", "positive finite"), ("malformed-fx-date", "timestamp,usdkrw\ninvalid,1400\n", "isoformat")):
        path = cases / f"{label}.csv"
        path.write_text(contents, encoding="utf-8")
        reject(label, [*historical, "--fx-history", str(path)], expected)
    (QA / f"{cases.name}.json").write_text(json.dumps({"frozen_output_bytes_unchanged": before == after, "cases": results}, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    assert all(row["pass"] for row in results), "CLI negative cases failed; inspect cli-cases.json"


if __name__ == "__main__":
    main()
