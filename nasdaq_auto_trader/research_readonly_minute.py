from __future__ import annotations

import csv
import json
import math
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .research_readonly import (
    MINUTE,
    SYMBOLS,
    JsonMap,
    JsonValue,
    Query,
    ReadOnlyKIS,
    ResearchError,
)
from .research_readonly_contract import rows_of


def normalize_minutes(rows: list[JsonValue], destination: Path, symbol: str) -> JsonMap:
    output: dict[str, list[str | float]] = {}
    timezone_matches = 0
    timezone_mismatches = 0
    invalid = 0
    duplicates = 0
    current_day_removed = 0
    regular: set[datetime] = set()
    for row in rows:
        if not isinstance(row, dict):
            invalid += 1
            continue
        try:
            local = datetime.strptime(
                str(row.get("xymd")) + str(row.get("xhms")), "%Y%m%d%H%M%S"
            ).replace(tzinfo=ZoneInfo("America/New_York"))
            korean = datetime.strptime(
                str(row.get("kymd")) + str(row.get("khms")), "%Y%m%d%H%M%S"
            ).replace(tzinfo=ZoneInfo("Asia/Seoul"))
            if local.astimezone(timezone.utc) == korean.astimezone(timezone.utc):
                timezone_matches += 1
            else:
                timezone_mismatches += 1
                continue
            if local.strftime("%Y%m%d") > "20260928":
                current_day_removed += 1
                continue
            op, high, low, close, volume = (
                float(str(row.get(key, "nan")))
                for key in ("open", "high", "low", "last", "evol")
            )
            if (
                not all(math.isfinite(v) for v in (op, high, low, close, volume))
                or min(op, high, low, close) <= 0
                or volume < 0
                or not low <= min(op, close) <= max(op, close) <= high
            ):
                raise ValueError
            stamp = local.astimezone(timezone.utc).isoformat()
            values: list[str | float] = [symbol, stamp, op, high, low, close, volume]
            if stamp in output:
                duplicates += 1
                if output[stamp] != values:
                    invalid += 1
                    continue
            output[stamp] = values
            if time(9, 30) <= local.time() < time(16):
                regular.add(local)
        except ValueError:
            invalid += 1
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("symbol", "timestamp", "open", "high", "low", "close", "volume")
        )
        writer.writerows(values for _, values in sorted(output.items()))
    expected: set[datetime] = set()
    for day in ("20260923", "20260924", "20260925", "20260928"):
        opening = datetime.strptime(day, "%Y%m%d").replace(
            hour=9, minute=30, tzinfo=ZoneInfo("America/New_York")
        )
        expected.update(opening + timedelta(minutes=5 * index) for index in range(78))
    stamps = sorted(output)
    return {
        "canonical_rows": len(output),
        "first_utc_label": stamps[0] if stamps else None,
        "last_utc_label": stamps[-1] if stamps else None,
        "duplicate_labels": duplicates,
        "invalid_rows": invalid,
        "timezone_pair_matches": timezone_matches,
        "timezone_pair_mismatches": timezone_mismatches,
        "current_day_rows_excluded": current_day_removed,
        "incident_regular_expected_5min_slots": len(expected),
        "incident_regular_missing_slots": len(expected - regular),
        "incident_regular_missing_ratio": len(expected - regular) / len(expected),
        "bar_timestamp_semantics": "provider_label; interval_open_vs_close_unconfirmed",
        "volume_field": "evol",
        "lookahead_caution": "only use after next label; no exact point-in-time incident replay",
    }


def minute(client: ReadOnlyKIS, private: Path, symbol: str) -> JsonMap:
    collected: list[JsonValue] = []
    cursor = ""
    status = "page_limit"
    timestamps: set[str] = set()
    try:
        for page in range(10):
            payload, _ = client.get(
                Query(
                    MINUTE,
                    "HHDFS76950200",
                    {
                        "AUTH": "",
                        "EXCD": SYMBOLS[symbol],
                        "SYMB": symbol,
                        "NMIN": "5",
                        "PINC": "1",
                        "NEXT": "1" if page else "",
                        "NREC": "120",
                        "FILL": "",
                        "KEYB": cursor,
                    },
                )
            )
            rows = rows_of(payload, "output2")
            collected.extend(rows)
            if not rows:
                status = "no_more_rows"
                break
            current = {
                str(row.get("xymd") or "") + str(row.get("xhms") or "") for row in rows
            }
            if any(len(stamp) != 14 or not stamp.isdigit() for stamp in current):
                raise ResearchError("minute_timestamp_fields_unconfirmed")
            if current.issubset(timestamps):
                raise ResearchError("minute_cursor_not_advancing")
            timestamps.update(current)
            oldest = min(current)
            if oldest <= "20260923093000":
                status = "incident_start_reached"
                break
            cursor = (
                datetime.strptime(oldest, "%Y%m%d%H%M%S").replace(
                    tzinfo=ZoneInfo("America/New_York")
                )
                - timedelta(minutes=5)
            ).strftime("%Y%m%d%H%M%S")
    except ResearchError as exc:
        status = str(exc)
    (private / f"{symbol}-minute-raw.json").write_text(
        json.dumps(collected, ensure_ascii=False), encoding="utf-8"
    )
    report: JsonMap = {
        "symbol": symbol,
        "status": status,
        "rows": len(collected),
        "unique_timestamps": len(timestamps),
        "first_local_bar": min(timestamps) if timestamps else None,
        "last_local_bar": max(timestamps) if timestamps else None,
        "timeframe": "5Min",
        "exact_incident_replay": False,
    }
    report["normalization"] = normalize_minutes(
        collected, private / f"{symbol}-5Min.csv", symbol
    )
    return report
