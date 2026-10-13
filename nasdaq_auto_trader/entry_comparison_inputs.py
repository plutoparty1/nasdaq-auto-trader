from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .exit_experiment import EvaluationSplit
from .exit_experiment_config import ExperimentInputError
from .exit_experiment_metrics import FxPoint
from .models import Bar


def explicit_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or ("T" not in value and " " not in value)
    ):
        raise ExperimentInputError(
            "source timestamp requires explicit time and timezone"
        )
    return parsed.astimezone(timezone.utc)


def validate_source_timestamps(path: Path, collected_at: str) -> None:
    collection = explicit_timestamp(collected_at)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            observed = explicit_timestamp(row["timestamp"])
            if observed > collection:
                raise ExperimentInputError(
                    "daily bar is later than recorded collection time"
                )


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
            price = 10 + index * 0.003 + math.sin(index / 15) * 0.4
            date = datetime(2020, 1, 1, 21, tzinfo=timezone.utc) + timedelta(days=index)
            writer.writerow(
                (
                    "SYNTHETIC",
                    date.isoformat(),
                    previous,
                    max(previous, price) + 0.02,
                    min(previous, price) - 0.02,
                    price,
                    100000 + index % 9 * 10000,
                )
            )
            previous = price


def load_fx(path: Path | None) -> tuple[FxPoint, ...]:
    if path is None:
        return ()
    points = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rate = float(row["usdkrw"])
            if not math.isfinite(rate) or rate <= 0:
                raise ExperimentInputError(
                    "FX history rates must be positive finite numbers"
                )
            points.append(FxPoint(timestamp(row["timestamp"]), rate))
    if not points or len({point.timestamp for point in points}) != len(points):
        raise ExperimentInputError(
            "FX history requires unique timestamps and at least one rate"
        )
    return tuple(sorted(points, key=lambda point: point.timestamp))


def build_splits(
    bars: dict[str, list[Bar]], train_end: str, validation_end: str
) -> tuple[EvaluationSplit, ...]:
    if any(len(history) < 80 for history in bars.values()):
        raise ExperimentInputError(
            "each symbol needs at least 80 daily bars including 64 warmup bars"
        )
    times = sorted({bar.timestamp for history in bars.values() for bar in history})
    evaluation_start = max(history[64].timestamp for history in bars.values())
    if not train_end < validation_end < times[-1]:
        raise ExperimentInputError(
            "frozen split boundaries must increase and final data must extend beyond validation"
        )
    windows = (
        EvaluationSplit("train", evaluation_start, train_end),
        EvaluationSplit(
            "validation",
            max(evaluation_start, next(value for value in times if value > train_end)),
            validation_end,
        ),
        EvaluationSplit(
            "final",
            max(
                evaluation_start,
                next(value for value in times if value > validation_end),
            ),
            times[-1],
        ),
    )
    return tuple(window for window in windows if window.start <= window.end)
