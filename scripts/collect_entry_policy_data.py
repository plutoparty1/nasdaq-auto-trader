# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: python scripts/collect_entry_policy_data.py --help
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
research_package = ModuleType("nasdaq_auto_trader")
research_package.__path__ = [str(repo_root / "nasdaq_auto_trader")]
sys.modules["nasdaq_auto_trader"] = research_package

from nasdaq_auto_trader.research_readonly import JsonMap, ReadOnlyKIS, ResearchError
from nasdaq_auto_trader.research_readonly_collect import daily, history, minute
from nasdaq_auto_trader.research_readonly_credentials import (
    load_credentials,
    private_output_root,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only KIS data collection. No broker, orders, cancellation or scheduling."
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Perform bounded authenticated read-only requests",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        required=True,
        help="Sanitized metadata destination; never private history",
    )
    args = parser.parse_args()
    target = args.summary.resolve()
    allowed_parent = (repo_root / "docs" / "entry-policy-audit-20260929").resolve()
    if target.parent != allowed_parent or target.suffix != ".json" or target.exists():
        print(json.dumps({"status": "summary_destination_denied"}))
        return 2
    report: JsonMap = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "KIS OpenAPI",
        "requested_daily_start": "2024-09-28",
        "requested_daily_end": "2026-09-28",
        "prespecified_symbols": ["CMCSA", "KDP", "HIVE", "SPY"],
        "SPY_role": "separate_broad_market_comparator",
        "orders_allowed": False,
        "cancel_allowed": False,
    }
    try:
        credentials = load_credentials(
            repo_root / "dist" / "NasdaqAutoTrader" / "config.kis.json"
        )
        report["credential_presence"] = "complete"
    except (ResearchError, OSError, ValueError):
        credentials = None
        report["credential_presence"] = "unavailable_or_invalid"
        report["collection_error"] = "local_configuration_unavailable"
    if args.collect and credentials is not None:
        try:
            private = private_output_root(repo_root) / datetime.now(
                timezone.utc
            ).strftime("%Y%m%dT%H%M%S%fZ")
            private.mkdir(parents=True, exist_ok=False)
            report["private_run_directory"] = str(private)
            (private / "collection-protocol.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            client = ReadOnlyKIS(credentials)
            try:
                client.authenticate()
                report["authentication"] = "success"
                report["history"] = history(client, private)
                report["daily"] = [
                    daily(client, private, symbol)
                    for symbol in ("CMCSA", "KDP", "HIVE", "SPY")
                ]
                report["minute"] = [
                    minute(client, private, symbol)
                    for symbol in ("CMCSA", "KDP", "HIVE")
                ]
            except ResearchError as exc:
                report["collection_error"] = str(exc)
            report["request_counts"] = dict(client.counts)
        except (OSError, ValueError):
            report["collection_error"] = "collection_storage_or_schema_error"
    report["status"] = (
        "unavailable"
        if "collection_error" in report
        else "collected_with_documented_limits"
        if args.collect
        else "presence_only"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                "status": report["status"],
                "collection_requested": args.collect,
                "request_counts": report.get("request_counts", {}),
            }
        )
    )
    return 2 if args.collect and "collection_error" in report else 0


if __name__ == "__main__":
    raise SystemExit(main())
