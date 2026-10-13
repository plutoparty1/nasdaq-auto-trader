# /// script
# requires-python = ">=3.11"
# dependencies = ["certifi", "tzdata"]
# ///
# How to run: python scripts/collect_public_entry_data.py --help
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from types import ModuleType
from urllib.parse import urlencode

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
# The application initializer imports live engines; research only loads pure modules.
package = ModuleType("nasdaq_auto_trader")
package.__path__ = [str(repo_root / "nasdaq_auto_trader")]
sys.modules["nasdaq_auto_trader"] = package

from nasdaq_auto_trader.research_public_bars import parse_yahoo_daily
from nasdaq_auto_trader.research_public_fx import parse_ecb_fx
from nasdaq_auto_trader.research_public_transport import (
    SYMBOLS,
    PublicDataError,
    public_get,
)


def main() -> int:
    if "--p1-receipt" in sys.argv[1:]:
        from nasdaq_auto_trader.p1_public_receipts import main as p1_main

        return p1_main(sys.argv[1:])
    parser = argparse.ArgumentParser(
        description="Read-only public daily stock and ECB FX collection; no broker credentials."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.environ["LOCALAPPDATA"])
        / "NasdaqAutoTrader/research/entry-policy-20260929/public",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(repo_root) or (
        output.exists() and (not output.is_dir() or any(output.iterdir()))
    ):
        parser.error("Use a fresh directory outside the repository")
    output.mkdir(parents=True, exist_ok=True)
    collected_at = datetime.now(timezone.utc).isoformat()
    stock_records = []
    combined_rows = []
    failures = []
    for symbol in SYMBOLS:
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            + symbol
            + "?"
            + urlencode(
                {
                    "period1": 1725148800,
                    "period2": 1790640000,
                    "interval": "1d",
                    "events": "div,splits",
                    "includeAdjustedClose": "true",
                }
            )
        )
        try:
            raw = public_get(url)
            (output / f"{symbol}.yahoo.json").write_bytes(raw)
            data = parse_yahoo_daily(raw, symbol, date(2024, 9, 1), date(2026, 9, 28))
            rows = [asdict(bar) for bar in data.bars]
            with (output / f"{symbol}.csv").open(
                "w", encoding="utf-8", newline=""
            ) as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            if symbol != "SPY":
                combined_rows.extend(rows)
            record = {
                "symbol": symbol,
                "source": url,
                "collected_at": collected_at,
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "csv_sha256": hashlib.sha256(
                    (output / f"{symbol}.csv").read_bytes()
                ).hexdigest(),
                "bars": len(rows),
                "first_timestamp": rows[0]["timestamp"],
                "last_timestamp": rows[-1]["timestamp"],
                "missing_dates": data.missing_dates,
                "missing_rate": len(data.missing_dates)
                / (len(rows) + len(data.missing_dates)),
                "excluded_outside_period": data.excluded_outside_period,
                "events": data.events,
                "adjusted_close_differs_count": sum(
                    adj is not None and abs(adj - bar.close) > 1e-8
                    for adj, bar in zip(data.adjusted_close, data.bars, strict=True)
                ),
            }
            stock_records.append(record)
            print(
                json.dumps(
                    {
                        "symbol": symbol,
                        "bars": len(rows),
                        "missing": len(data.missing_dates),
                        "first": rows[0]["timestamp"],
                        "last": rows[-1]["timestamp"],
                        "splits": data.events.get("splits", {}),
                    }
                )
            )
        except PublicDataError as error:
            failures.append({"source": symbol, "reason": str(error)})
        time.sleep(0.6)
    if combined_rows:
        with (output / "actual_trade_group.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(combined_rows[0]))
            writer.writeheader()
            writer.writerows(
                sorted(combined_rows, key=lambda row: (row["timestamp"], row["symbol"]))
            )
    fx_record = None
    fx_url = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD+KRW.EUR.SP00.A?startPeriod=2024-08-30&endPeriod=2026-09-28&format=csvdata"
    try:
        raw_fx = public_get(fx_url)
        (output / "ecb-source.csv").write_bytes(raw_fx)
        points = parse_ecb_fx(raw_fx)
        with (output / "usdkrw.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("timestamp", "usdkrw"))
            writer.writeheader()
            writer.writerows(asdict(point) for point in points)
        fx_record = {
            "source": fx_url,
            "collected_at": collected_at,
            "rows": len(points),
            "first": asdict(points[0]),
            "last": asdict(points[-1]),
            "raw_sha256": hashlib.sha256(raw_fx).hexdigest(),
            "csv_sha256": hashlib.sha256(
                (output / "usdkrw.csv").read_bytes()
            ).hexdigest(),
        }
        print(
            json.dumps(
                {
                    "fx_rows": len(points),
                    "first": points[0].timestamp,
                    "last": points[-1].timestamp,
                }
            )
        )
    except PublicDataError as error:
        failures.append({"source": "ECB", "reason": str(error)})
    manifest = {
        "collected_at": collected_at,
        "requested_start": "2024-09-01",
        "requested_end": "2026-09-28",
        "timeframe": "1Day",
        "price_policy": "Yahoo quote OHLC: split-adjusted, not dividend-adjusted; raw events retained. No total-return claim. Split spans require separate handling before comparisons.",
        "timestamp_policy": "Exchange completed-session close in America/New_York converted to UTC; NYSE verified 2024-2026 calendar incl early closes and 2025-01-09 closure. Daily labels, not actual fill timestamps.",
        "fx_policy": "ECB KRW per EUR / USD per EUR; same-day 16:00 UTC conservative availability label, actual trade FX unknown.",
        "order_calls": 0,
        "cancel_calls": 0,
        "credential_reads": 0,
        "transport": "exact HTTPS GET allowlist; TLS certifi verification; no redirects; at most 2 attempts per query",
        "stocks": stock_records,
        "fx": fx_record,
        "failures": failures,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "failures": failures,
                "stocks": len(stock_records),
                "order_calls": 0,
                "cancel_calls": 0,
            }
        )
    )
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
