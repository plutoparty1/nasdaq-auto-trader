# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python scripts/run_exit_experiments.py --help
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType


class OfflineNetworkError(RuntimeError):
    pass


def deny_network(event: str, args: tuple[str, ...]) -> None:
    if event.startswith("socket.") or event in (
        "http.client.connect",
        "urllib.Request",
        "subprocess.Popen",
    ):
        raise OfflineNetworkError(
            "network and subprocess access are forbidden in the experiment runner"
        )


sys.addaudithook(deny_network)
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
# Bypass the application package initializer, which imports live engine/config modules.
offline_package = ModuleType("nasdaq_auto_trader")
offline_package.__path__ = [str(repo_root / "nasdaq_auto_trader")]
sys.modules["nasdaq_auto_trader"] = offline_package

from nasdaq_auto_trader.data import load_bars_csv
from nasdaq_auto_trader.exit_experiment import EvaluationSplit, run_suite
from nasdaq_auto_trader.exit_experiment_config import (
    ExperimentInputError,
    load_provenance,
    load_settings,
)
from nasdaq_auto_trader.exit_experiment_metrics import FxPoint


def timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (
        parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
        .astimezone(timezone.utc)
        .isoformat()
    )


def make_smoke(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("symbol", "timestamp", "open", "high", "low", "close", "volume")
        )
        previous = 10.0
        for index in range(300):
            price = (
                10
                + index * 0.008
                + math.sin(index / 15) * 1.5
                + math.sin(index / 3) * 0.12
            )
            date = datetime(2020, 1, 1, 21, tzinfo=timezone.utc) + timedelta(days=index)
            writer.writerow(
                (
                    "SYNTHETIC",
                    date.isoformat(),
                    previous,
                    max(previous, price) * 1.005,
                    min(previous, price) * 0.995,
                    price,
                    100000 + index % 9 * 10000,
                )
            )
            previous = price


def load_fx(path: Path | None) -> tuple[FxPoint, ...]:
    if path is None:
        return ()
    points: list[FxPoint] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rate = float(row["usdkrw"])
            if not math.isfinite(rate) or rate <= 0:
                raise ExperimentInputError("FX rates must be finite and positive")
            points.append(FxPoint(timestamp(row["timestamp"]), rate))
    if not points or len({point.timestamp for point in points}) != len(points):
        raise ExperimentInputError("FX history must be nonempty with unique timestamps")
    return tuple(sorted(points, key=lambda point: point.timestamp))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OFFLINE ONLY: prespecified 80000 KRW exit comparisons"
    )
    parser.add_argument(
        "--settings", type=Path, default=Path("experiments/early_exit/settings.json")
    )
    parser.add_argument("--bars", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--usdkrw", type=float, required=True)
    parser.add_argument("--fx-source", required=True)
    parser.add_argument("--fx-as-of", required=True)
    parser.add_argument("--fx-history", type=Path)
    parser.add_argument("--train-end")
    parser.add_argument("--validation-end")
    parser.add_argument("--monthly-operations-krw", type=float)
    parser.add_argument("--compare-entry-gate", action="store_true")
    parser.add_argument("--synthetic-smoke", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.usdkrw) or args.usdkrw <= 0:
        raise ExperimentInputError("positive finite USD/KRW is required")
    if args.monthly_operations_krw is not None and (
        not math.isfinite(args.monthly_operations_krw)
        or args.monthly_operations_krw < 0
    ):
        raise ExperimentInputError(
            "monthly operations cost must be finite and nonnegative"
        )
    if not args.fx_source.strip():
        raise ExperimentInputError("FX source must not be blank")
    fx_as_of = timestamp(args.fx_as_of)
    settings = load_settings(args.settings)
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "protocol.json").exists():
        raise ExperimentInputError(
            "output already contains a frozen protocol; choose a fresh directory"
        )
    if args.synthetic_smoke:
        bars_path = args.output / "synthetic-bars.csv"
        make_smoke(bars_path)
        provenance = {
            "synthetic": True,
            "data_source": "generated smoke fixture; not historical evidence",
        }
    else:
        if (
            args.bars is None
            or args.provenance is None
            or not args.train_end
            or not args.validation_end
        ):
            raise ExperimentInputError(
                "historical runs require bars, provenance, train-end and validation-end"
            )
        from dataclasses import asdict

        provenance = asdict(load_provenance(args.provenance))
        if any("REPLACE" in str(value) for value in provenance.values()):
            raise ExperimentInputError(
                "replace all provenance placeholders before historical runs"
            )
        bars_path = args.bars
    bars = load_bars_csv(bars_path)
    times = sorted({bar.timestamp for history in bars.values() for bar in history})
    if len(times) < 10:
        raise ExperimentInputError(
            "at least ten timestamps are required even for smoke execution"
        )
    train_end = (
        timestamp(args.train_end) if args.train_end else times[int(len(times) * 0.6)]
    )
    validation_end = (
        timestamp(args.validation_end)
        if args.validation_end
        else times[int(len(times) * 0.8)]
    )
    if not times[0] < train_end < validation_end < times[-1]:
        raise ExperimentInputError(
            "split boundaries must increase strictly inside the supplied data"
        )
    if (
        not args.synthetic_smoke
        and timestamp(str(provenance["universe_as_of"])) > times[0]
    ):
        raise ExperimentInputError(
            "universe provenance must predate the first evaluated timestamp"
        )
    splits = (
        EvaluationSplit("train", times[0], train_end),
        EvaluationSplit(
            "validation",
            next(value for value in times if value > train_end),
            validation_end,
        ),
        EvaluationSplit(
            "final", next(value for value in times if value > validation_end), times[-1]
        ),
    )
    history = load_fx(args.fx_history)
    if history and history[0].timestamp > times[0]:
        raise ExperimentInputError(
            "historical FX needs a rate at or before the first data timestamp"
        )
    run_suite(
        settings,
        bars,
        splits,
        args.output,
        fx_rate=args.usdkrw,
        fx_history=history,
        operations_monthly_krw=args.monthly_operations_krw,
        compare_entry_gate=args.compare_entry_gate,
    )
    manifest = {
        "bars_sha256": hashlib.sha256(bars_path.read_bytes()).hexdigest(),
        "settings_sha256": hashlib.sha256(args.settings.read_bytes()).hexdigest(),
        "provenance": provenance,
        "fx_source": args.fx_source.strip(),
        "fx_as_of": fx_as_of,
        "fx_history_sha256": hashlib.sha256(args.fx_history.read_bytes()).hexdigest()
        if args.fx_history
        else None,
        "timestamp_count": len(times),
        "symbols": sorted(bars),
        "assessment": "SYNTHETIC_SMOKE_ONLY"
        if args.synthetic_smoke
        else "EXPLORATORY_REQUIRES_PROVENANCE_REVIEW",
        "limitations": [
            "No current learned-universe or daily-minimum selection replay",
            "Day bars cannot establish intraday protective order sequence",
            "Partial first/last months are observation windows, not complete calendar month evidence",
            "Monthly +10% incidence is a past sample observation, not future probability",
            "Zero executions never establishes strategy quality; data/server/AI cost unknown unless explicitly supplied",
        ],
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Offline comparison written to {args.output}; {manifest['assessment']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
