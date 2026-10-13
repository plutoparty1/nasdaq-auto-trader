"""Parse immutable public receipts; provider time and local receipt time remain distinct."""

from __future__ import annotations

import csv
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import isfinite
from pathlib import Path
from urllib.parse import urlsplit

from .data import load_bars_csv
from .entry_comparison import JsonValue
from .entry_comparison_inputs import load_fx
from .exit_experiment import validate_daily_bars
from .exit_experiment_config import ExperimentInputError
from .exit_experiment_metrics import FxPoint
from .models import Bar
from .p1_paper_codec import read_json
from .p1_paper_protocol import SYMBOLS, PaperProtocol, digest, mapping, text_field, utc
from .research_public_transport import (
    PublicDataError,
    PublicRequestBounds,
    validate_public_request,
)


@dataclass(frozen=True, slots=True)
class PaperReceipt:
    sha256: str
    path: Path
    bars: dict[str, list[Bar]]
    fx: tuple[FxPoint, ...]
    received_at: dict[str, str]
    fx_received_at: str | None
    failures: tuple[str, ...]
    split_dates: tuple[str, ...]


def _raw_received(
    row: Mapping[str, JsonValue],
    filename: str,
    files: Mapping[str, JsonValue],
    bounds: PublicRequestBounds,
    created: datetime,
) -> str | None:
    started = utc(text_field(row.get("request_started_at")))
    if not bounds.now <= started <= created:
        raise ExperimentInputError("paper_receipt_clock_invalid")
    source = text_field(row.get("source"))
    expected_path = (
        "/service/data/EXR/D.USD+KRW.EUR.SP00.A"
        if filename == "ecb-source.csv"
        else "/v8/finance/chart/" + filename.split(".")[0]
    )
    try:
        validate_public_request("GET", source, bounds=bounds)
        if urlsplit(source).path != expected_path:
            raise PublicDataError("public_endpoint_denied")
    except (PublicDataError, ValueError):
        raise ExperimentInputError("paper_receipt_source_invalid") from None
    if row.get("raw_file") != filename:
        raise ExperimentInputError("paper_receipt_raw_file_invalid")
    stamp = row.get("received_at")
    if stamp is None:
        if row.get("raw_sha256") is not None or filename in files:
            raise ExperimentInputError("paper_receipt_raw_without_response")
        return None
    received = text_field(stamp)
    if not started <= utc(received) <= created:
        raise ExperimentInputError("paper_receipt_clock_invalid")
    if filename not in files or row.get("raw_sha256") != files[filename]:
        raise ExperimentInputError("paper_receipt_raw_hash_invalid")
    return received


def _has_rows(path: Path, fields: tuple[str, ...]) -> bool:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(fields):
            raise ExperimentInputError("paper_receipt_csv_columns_invalid")
        return next(reader, None) is not None


def read_receipt(path: Path, protocol: PaperProtocol, now: datetime) -> PaperReceipt:
    raw = read_json(path.read_text(encoding="utf-8"))
    data = mapping(raw)
    if data.get("schema_version") != 1 or data.get("kind") != "P1_PUBLIC_DAILY":
        raise ExperimentInputError("paper_receipt_schema_invalid")
    if data.get("calendar_sha256") != protocol.raw.get("calendar_sha256"):
        raise ExperimentInputError("paper_receipt_calendar_mismatch")
    requested = utc(text_field(data.get("request_started_at")))
    created = utc(text_field(data.get("created_at")))
    if not requested <= created <= utc(now.isoformat()):
        raise ExperimentInputError("paper_receipt_clock_invalid")
    start = date.fromisoformat(text_field(data.get("requested_start")))
    end = date.fromisoformat(text_field(data.get("requested_end")))
    if start != requested.date() - timedelta(days=200) or end != requested.date():
        raise ExperimentInputError("paper_receipt_period_invalid")
    bounds = PublicRequestBounds(start, end, requested)
    failures_raw = data.get("failures")
    if not isinstance(failures_raw, list) or any(
        not isinstance(v, str) for v in failures_raw
    ):
        raise ExperimentInputError("paper_receipt_failures_invalid")
    failures = tuple(text_field(v) for v in failures_raw)
    files = mapping(data.get("files"))
    allowed = {
        "bars.csv",
        "usdkrw.csv",
        "CMCSA.yahoo.json",
        "HIVE.yahoo.json",
        "KDP.yahoo.json",
        "ecb-source.csv",
    }
    if not {"bars.csv", "usdkrw.csv"} <= files.keys() or not files.keys() <= allowed:
        raise ExperimentInputError("paper_receipt_file_set_invalid")
    for name, expected in files.items():
        source = path.parent / name
        if (
            source.is_symlink()
            or not source.is_file()
            or source.stat().st_size > 8_000_000
            or not isinstance(expected, str)
            or re.fullmatch(r"[a-f0-9]{64}", expected) is None
            or digest(source) != expected
        ):
            raise ExperimentInputError("paper_receipt_content_hash_invalid")
    stock_rows = data.get("stocks")
    if not isinstance(stock_rows, list) or len(stock_rows) != len(SYMBOLS):
        raise ExperimentInputError("paper_receipt_stocks_invalid")
    received: dict[str, str] = {}
    seen: set[str] = set()
    split_dates: list[str] = []
    for raw_stock in stock_rows:
        stock = mapping(raw_stock)
        symbol = text_field(stock.get("symbol"))
        if symbol not in SYMBOLS or symbol in seen:
            raise ExperimentInputError("paper_receipt_universe_or_duplicate_invalid")
        seen.add(symbol)
        stamp = _raw_received(stock, f"{symbol}.yahoo.json", files, bounds, created)
        if stamp is None:
            continue
        received[symbol] = stamp
        events = mapping(stock.get("events", {}))
        for event in mapping(events.get("splits", {})).values():
            date_value = mapping(event).get("date")
            if (
                isinstance(date_value, (int, float))
                and not isinstance(date_value, bool)
                and isfinite(date_value)
            ):
                try:
                    split_dates.append(
                        datetime.fromtimestamp(date_value, requested.tzinfo)
                        .date()
                        .isoformat()
                    )
                except (ValueError, OverflowError, OSError):
                    raise ExperimentInputError("paper_split_event_invalid") from None
            else:
                raise ExperimentInputError("paper_split_event_invalid")
    has_bars = _has_rows(
        path.parent / "bars.csv",
        ("symbol", "timestamp", "open", "high", "low", "close", "volume"),
    )
    bars = load_bars_csv(path.parent / "bars.csv") if has_bars else {}
    for symbol in SYMBOLS:
        if symbol not in bars and not any(
            v.startswith((symbol + ":", symbol + ".yahoo.json:")) for v in failures
        ):
            raise ExperimentInputError("paper_receipt_missing_stock_without_failure")
    if not bars.keys() <= set(SYMBOLS):
        raise ExperimentInputError("paper_receipt_universe_invalid")
    calendar = {s.close_at for s in protocol.sessions}
    for symbol, history in bars.items():
        if symbol not in received or any(
            bar.timestamp not in calendar
            or utc(bar.timestamp) > min(utc(received[symbol]), requested)
            for bar in history
        ):
            raise ExperimentInputError("paper_bar_not_available_at_receipt")
    validate_daily_bars(bars)
    fx: tuple[FxPoint, ...] = ()
    fx_received = _raw_received(
        mapping(data.get("fx")),
        "ecb-source.csv",
        files,
        PublicRequestBounds(end - timedelta(days=14), end, requested),
        created,
    )
    if _has_rows(path.parent / "usdkrw.csv", ("timestamp", "usdkrw")):
        if fx_received is None:
            raise ExperimentInputError("paper_fx_without_response")
        fx = load_fx(path.parent / "usdkrw.csv")
        if any(utc(point.timestamp) > min(utc(fx_received), requested) for point in fx):
            raise ExperimentInputError("paper_fx_not_available_at_receipt")
    elif not any(v.startswith(("ECB:", "ecb-source.csv:")) for v in failures):
        raise ExperimentInputError("paper_receipt_empty_fx_without_failure")
    return PaperReceipt(
        digest(path),
        path.resolve(),
        bars,
        fx,
        received,
        fx_received,
        failures,
        tuple(split_dates),
    )
