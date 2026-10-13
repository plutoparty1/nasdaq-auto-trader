from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final
from urllib.parse import urlencode

from .p1_public_receipt_types import (
    Clock,
    PublicFetcher,
    RawReceipt,
    Receipt,
    StockReceipt,
    clock_utc,
    load_calendar,
    utc_now,
)
from .research_public_bars import PublicBar, parse_yahoo_daily
from .research_public_fx import PublicFx, parse_ecb_fx
from .research_public_transport import (
    P1_SYMBOLS,
    PublicDataError,
    PublicRequestBounds,
    public_get,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[1]


class ReceiptArguments(argparse.Namespace):
    output: Path = REPO_ROOT
    calendar: Path = REPO_ROOT


def _receive(
    directory: Path,
    filename: str,
    url: str,
    bounds: PublicRequestBounds,
    clock: Clock,
    fetch: PublicFetcher,
    failures: list[str],
) -> tuple[RawReceipt, bytes | None]:
    started = clock_utc(clock)
    record: RawReceipt = {
        "source": url,
        "request_started_at": started.isoformat(),
        "received_at": None,
        "raw_file": filename,
        "raw_sha256": None,
    }
    try:
        raw = fetch(url, bounds=bounds)
        received = clock_utc(clock)
        record["received_at"] = received.isoformat()
        record["raw_sha256"] = hashlib.sha256(raw).hexdigest()
        with (directory / filename).open("xb") as handle:
            _ = handle.write(raw)
        if received < started:
            raise PublicDataError("public_clock_went_backwards")
        return record, raw
    except PublicDataError as error:
        failures.append(f"{filename}:{error}")
        return record, None


def collect_receipt(
    output: Path,
    calendar_path: Path,
    *,
    clock: Clock = utc_now,
    fetch: PublicFetcher = public_get,
) -> Receipt:
    destination = output.resolve()
    if destination.is_relative_to(REPO_ROOT) or destination.exists():
        raise PublicDataError("public_output_must_be_fresh_outside_repository")
    calendar = load_calendar(calendar_path)
    requested = clock_utc(clock)
    start, end = requested.date() - timedelta(days=200), requested.date()
    bounds = PublicRequestBounds(start, end, requested)
    if not any(
        start.isoformat() <= day <= end.isoformat() and close <= requested
        for day, close in calendar.sessions.items()
    ):
        raise PublicDataError("public_calendar_no_completed_sessions")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{destination.name}-", dir=destination.parent
    ) as temporary:
        directory = Path(temporary)
        failures: list[str] = []
        stocks: list[StockReceipt] = []
        bars: list[PublicBar] = []
        for symbol in P1_SYMBOLS:
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?"
                + urlencode(
                    {
                        "period1": int(
                            datetime.combine(start, time(), UTC).timestamp()
                        ),
                        "period2": int(requested.timestamp()),
                        "interval": "1d",
                        "events": "div,splits",
                        "includeAdjustedClose": "true",
                    }
                )
            )
            raw_record, raw = _receive(
                directory, f"{symbol}.yahoo.json", url, bounds, clock, fetch, failures
            )
            stock: StockReceipt = {
                **raw_record,
                "symbol": symbol,
                "missing_dates": [],
                "events": {},
            }
            if raw is not None:
                try:
                    data = parse_yahoo_daily(
                        raw,
                        symbol,
                        start,
                        end,
                        sessions=calendar.sessions,
                        completed_at=requested,
                    )
                    bars.extend(data.bars)
                    stock["missing_dates"] = list(data.missing_dates)
                    stock["events"] = data.events
                    if data.missing_dates:
                        failures.append(f"{symbol}:public_sessions_missing")
                except PublicDataError as error:
                    failures.append(f"{symbol}:{error}")
            stocks.append(stock)
        fx_start = end - timedelta(days=14)
        fx_url = (
            "https://data-api.ecb.europa.eu/service/data/EXR/D.USD+KRW.EUR.SP00.A?"
            + urlencode(
                {
                    "startPeriod": fx_start.isoformat(),
                    "endPeriod": end.isoformat(),
                    "format": "csvdata",
                }
            )
        )
        fx, raw_fx = _receive(
            directory,
            "ecb-source.csv",
            fx_url,
            PublicRequestBounds(fx_start, end, requested),
            clock,
            fetch,
            failures,
        )
        points: tuple[PublicFx, ...] = ()
        if raw_fx is not None:
            try:
                points = tuple(
                    point
                    for point in parse_ecb_fx(raw_fx, start=fx_start, end=end)
                    if datetime.fromisoformat(point.timestamp) <= requested
                )
                if not points:
                    raise PublicDataError("public_fx_no_available_rows")
            except PublicDataError as error:
                failures.append(f"ECB:{error}")
        with (directory / "bars.csv").open("x", encoding="utf-8", newline="") as handle:
            writer: csv.DictWriter[str] = csv.DictWriter(
                handle,
                fieldnames=(
                    "symbol",
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ),
            )
            writer.writeheader()
            writer.writerows(
                asdict(bar)
                for bar in sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol))
            )
        with (directory / "usdkrw.csv").open(
            "x", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=("timestamp", "usdkrw"))
            writer.writeheader()
            writer.writerows(asdict(point) for point in points)
        receipt: Receipt = {
            "schema_version": 1,
            "kind": "P1_PUBLIC_DAILY",
            "request_started_at": requested.isoformat(),
            "created_at": clock_utc(clock).isoformat(),
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "calendar_sha256": calendar.sha256,
            "files": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(directory.iterdir())
            },
            "stocks": stocks,
            "fx": fx,
            "failures": failures,
        }
        with (directory / "receipt.json").open("x", encoding="utf-8") as handle:
            json.dump(receipt, handle, indent=2, allow_nan=False)
        _ = directory.rename(destination)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manually collect a fixed P1 daily public-data receipt."
    )
    _ = parser.add_argument("--p1-receipt", action="store_true", required=True)
    _ = parser.add_argument("--collect", action="store_true", required=True)
    _ = parser.add_argument("--output", type=Path, required=True)
    _ = parser.add_argument("--calendar", type=Path, required=True)
    args = ReceiptArguments()
    _ = parser.parse_args(argv, namespace=args)
    try:
        receipt = collect_receipt(args.output, args.calendar)
    except (PublicDataError, OSError) as error:
        parser.exit(2, f"P1 collection refused: {error}\n")
    print(
        json.dumps(
            {"output": str(args.output.resolve()), "failures": receipt["failures"]}
        )
    )
    return int(bool(receipt["failures"]))
