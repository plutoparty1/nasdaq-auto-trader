# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python scripts/run_entry_policy_comparison.py --help
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType


class OfflineNetworkError(RuntimeError):
    pass


def deny_network(event: str, args: tuple[JsonValue, ...]) -> None:
    if event.startswith("socket.") or event in (
        "http.client.connect",
        "urllib.Request",
        "subprocess.Popen",
    ):
        raise OfflineNetworkError(
            "network and subprocess access are forbidden in entry comparison"
        )


sys.addaudithook(deny_network)
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
# Application initialization imports live brokers, so this CLI exposes only pure modules.
offline_package = ModuleType("nasdaq_auto_trader")
offline_package.__path__ = [str(repo_root / "nasdaq_auto_trader")]
sys.modules["nasdaq_auto_trader"] = offline_package

from nasdaq_auto_trader.data import load_bars_csv
from nasdaq_auto_trader.entry_comparison import (
    JsonValue,
    load_entry_profile,
    run_entry_suite,
)
from nasdaq_auto_trader.entry_comparison_inputs import (
    build_splits,
    load_fx,
    make_smoke,
    timestamp,
    validate_source_timestamps,
)
from nasdaq_auto_trader.exit_experiment_config import (
    ExperimentInputError,
    load_settings,
)


def main() -> int:
    if "--p1-paper" in sys.argv[1:]:
        from nasdaq_auto_trader.p1_paper_cli import main as paper_main
        return paper_main(sys.argv[1:])
    parser = argparse.ArgumentParser(
        description="OFFLINE ONLY: matched-risk A/B/C entry policy comparison",
        epilog="P1 paper account: --p1-paper {init,resume,status} --paper-dir PATH [--receipt PATH]"
    )
    parser.add_argument(
        "--profile", type=Path, default=Path("experiments/entry_policy/profile.json")
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
    cohort = parser.add_mutually_exclusive_group()
    cohort.add_argument("--control", action="store_true")
    cohort.add_argument("--action-free-pair", action="store_true")
    parser.add_argument("--synthetic-smoke", action="store_true")
    parser.add_argument("--profitability-profile", type=Path, help="Frozen offline profitability or three-profile sizing experiment")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="entry-comparison-") as staging:
        return execute(args, Path(staging))


def execute(args: argparse.Namespace, staging: Path) -> int:
    if not math.isfinite(args.usdkrw) or args.usdkrw <= 0 or not args.fx_source.strip():
        raise ExperimentInputError(
            "positive USD/KRW and nonblank FX source are required"
        )
    if args.monthly_operations_krw is not None and (
        not math.isfinite(args.monthly_operations_krw)
        or args.monthly_operations_krw < 0
    ):
        raise ExperimentInputError("operations cost must be finite and nonnegative")
    fx_as_of = timestamp(args.fx_as_of)
    config = load_entry_profile(args.profile)
    cost_path = repo_root / "experiments/early_exit/settings.json"
    costs = load_settings(cost_path).costs
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ExperimentInputError(
            "output must be an empty directory; existing files cannot be overwritten"
        )
    if args.synthetic_smoke:
        bars_path = staging / "synthetic-bars.csv"
        make_smoke(bars_path)
        provenance: dict[str, JsonValue] = {
            "synthetic": True,
            "data_source": "generated test fixture, not market evidence",
        }
    else:
        if (
            args.bars is None
            or args.provenance is None
            or not args.train_end
            or not args.validation_end
        ):
            raise ExperimentInputError(
                "historical runs need bars, provenance and both frozen split dates"
            )
        bars_path = args.bars
        provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
        for name in (
            "data_source",
            "bar_interval",
            "adjustment_policy",
            "universe_source",
            "collected_at",
        ):
            value = provenance.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ExperimentInputError(
                    f"nonblank historical provenance {name} is required"
                )
        if provenance["bar_interval"] != "1Day":
            raise ExperimentInputError(
                "1Day signal bars are required; intraday bars cannot substitute"
            )
        collected_at = provenance["collected_at"]
        if not isinstance(collected_at, str):
            raise ExperimentInputError("collection timestamp must be text")
        validate_source_timestamps(bars_path, collected_at)
    loaded = load_bars_csv(bars_path)
    requested = (
        {"SYNTHETIC"}
        if args.synthetic_smoke
        else (
            {"SPY"}
            if args.control
            else (
                {"KDP", "HIVE"} if args.action_free_pair else {"CMCSA", "KDP", "HIVE"}
            )
        )
    )
    if not requested.issubset(loaded):
        raise ExperimentInputError(
            "data must contain every symbol in the frozen case cohort or SPY control"
        )
    bars = {symbol: loaded[symbol] for symbol in sorted(requested)}
    times = sorted({bar.timestamp for history in bars.values() for bar in history})
    if len(times) < 80:
        raise ExperimentInputError(
            "at least 80 daily observations are needed including warmup"
        )
    train_end = (
        timestamp(args.train_end) if args.train_end else times[int(len(times) * 0.6)]
    )
    validation_end = (
        timestamp(args.validation_end)
        if args.validation_end
        else times[int(len(times) * 0.8)]
    )
    splits = build_splits(bars, train_end, validation_end)
    fx_history = load_fx(args.fx_history)
    if fx_history and fx_history[0].timestamp > splits[0].start:
        raise ExperimentInputError(
            "FX history must include a rate before the first evaluation"
        )
    manifest: dict[str, JsonValue] = {
        "bars_sha256": hashlib.sha256(bars_path.read_bytes()).hexdigest(),
        "profile_sha256": hashlib.sha256(args.profile.read_bytes()).hexdigest(),
        "costs_sha256": hashlib.sha256(cost_path.read_bytes()).hexdigest(),
        "fx_history_sha256": hashlib.sha256(args.fx_history.read_bytes()).hexdigest()
        if args.fx_history
        else None,
        "fx_source": args.fx_source.strip(),
        "fx_as_of": fx_as_of,
        "provenance": provenance,
        "symbols": [symbol for symbol in sorted(bars)],
        "bar_count": {symbol: len(history) for symbol, history in bars.items()},
        "assessment": "SYNTHETIC_SMOKE_ONLY"
        if args.synthetic_smoke
        else "HISTORICAL_CASE_COHORT_MATCHED_RISK_PROXY",
        "unavailable_splits": [
            name
            for name in ("train", "validation", "final")
            if name not in {split.name for split in splits}
        ],
        "omitted_split_reason": "insufficient data after fixed 64-bar warmup; boundaries not retuned",
        "order_api_calls": 0,
        "cancel_api_calls": 0,
        "limitations": [
            "A omits historical forced-entry 5% risk override; all policies use 1%",
            "Fixed case cohort is selected with hindsight, not a historical universe selection replay",
            "Daily signals and fills cannot measure the historical five-minute liquidation mechanism",
            "Dividend cash is excluded; provider price adjustment policy must be reviewed",
            "Known charges use assumptions; actual account fees and operations cost unverified",
            "Zero executions and partial-month returns do not establish strategy quality",
        ],
    }
    runner = run_entry_suite
    if args.profitability_profile is not None:
        from nasdaq_auto_trader.profitability_experiment import run_profitability_suite
        from nasdaq_auto_trader.sizing_entry_config import SIZING_PROFILE_SHA

        if hashlib.sha256(args.profitability_profile.read_bytes()).hexdigest() == SIZING_PROFILE_SHA:
            from nasdaq_auto_trader.sizing_entry_experiment import (
                run_sizing_entry_suite,
            )

            runner = partial(run_sizing_entry_suite, profile_path=args.profitability_profile)
        else:
            runner = partial(run_profitability_suite, profile_path=args.profitability_profile)
    runner(
        config,
        bars,
        splits,
        args.output,
        costs,
        fx_rate=args.usdkrw,
        manifest=manifest,
        fx_history=fx_history,
        operations_monthly_krw=args.monthly_operations_krw,
    )
    if args.synthetic_smoke:
        (args.output / "synthetic-bars.csv").write_bytes(bars_path.read_bytes())
    print(
        f"Offline comparison written to {args.output}; "
        + ("EXPLORATORY_ALREADY_USED_DATA" if args.profitability_profile and not args.synthetic_smoke else str(manifest["assessment"]))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
