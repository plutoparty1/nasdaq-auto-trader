from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit

import pytest

from nasdaq_auto_trader import p1_public_receipts as receipts
from nasdaq_auto_trader import research_public_transport as transport
from nasdaq_auto_trader.research_public_bars import parse_yahoo_daily
from nasdaq_auto_trader.research_public_fx import parse_ecb_fx

NOW = datetime(2026, 10, 9, 21, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


def yahoo_url(
    symbol: str = "CMCSA", start: date = date(2026, 4, 1), end: datetime = NOW
) -> str:
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?" + urlencode(
        {
            "period1": int(
                datetime.combine(start, datetime.min.time(), UTC).timestamp()
            ),
            "period2": int(end.timestamp()),
            "interval": "1d",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        }
    )


def test_future_transport_mode_is_explicit_and_legacy_remains_closed():
    # Given a request beyond the historical collector range.
    bounds = transport.PublicRequestBounds(date(2026, 4, 1), NOW.date(), NOW)
    # When the opt-in boundary is supplied, only that boundary is extended.
    transport.validate_public_request("GET", yahoo_url(), bounds=bounds)
    # Then the original default still rejects this future range.
    with pytest.raises(transport.PublicDataError):
        transport.validate_public_request("GET", yahoo_url())


@pytest.mark.parametrize(
    "symbol,method,end",
    [
        ("SPY", "GET", NOW),
        ("AAPL", "GET", NOW),
        ("CMCSA", "POST", NOW),
        ("CMCSA", "GET", NOW + timedelta(seconds=1)),
    ],
)
def test_bounded_transport_rejects_outside_scope(
    symbol: str, method: str, end: datetime
):
    bounds = transport.PublicRequestBounds(date(2026, 4, 1), NOW.date(), NOW)
    with pytest.raises(transport.PublicDataError):
        transport.validate_public_request(
            method, yahoo_url(symbol, end=end), bounds=bounds
        )


@pytest.mark.parametrize(
    "start,end",
    [
        (date(2025, 1, 1), NOW.date()),
        (NOW.date(), date(2026, 10, 10)),
        (date(2026, 10, 10), NOW.date()),
    ],
)
def test_bounds_reject_long_reversed_or_future_dates(start: date, end: date):
    with pytest.raises(transport.PublicDataError):
        transport.PublicRequestBounds(start, end, NOW)


def yahoo_payload(symbol: str, days: tuple[int, ...] = (8, 9)) -> bytes:
    return json.dumps(
        {
            "chart": {
                "error": None,
                "result": [
                    {
                        "meta": {
                            "symbol": symbol,
                            "currency": "USD",
                            "exchangeTimezoneName": "America/New_York",
                        },
                        "timestamp": [
                            int(datetime(2026, 10, day, 13, 30, tzinfo=UTC).timestamp())
                            for day in days
                        ],
                        "indicators": {
                            "quote": [
                                {
                                    key: [value] * len(days)
                                    for key, value in {
                                        "open": 10,
                                        "high": 11,
                                        "low": 9,
                                        "close": 10,
                                        "volume": 100,
                                    }.items()
                                }
                            ]
                        },
                        "events": {
                            "splits": {"one": {"date": 1791552600, "splitRatio": "2:1"}}
                        },
                    }
                ],
            }
        }
    ).encode()


def calendar_file(tmp_path: Path, *, duplicate: bool = False) -> Path:
    calendar = tmp_path / "sessions.csv"
    rows = "session_date,open_at,close_at\n"
    for day in (8, 9, 9) if duplicate else (8, 9, 12):
        rows += f"2026-10-{day:02},2026-10-{day:02}T13:30:00+00:00,2026-10-{day:02}T20:00:00+00:00\n"
    calendar.write_text(rows, encoding="utf-8")
    return calendar


def test_collector_retains_raw_hashes_events_and_after_response_times(tmp_path: Path):
    # Given a fake wire whose clock advances during each request.
    calendar = calendar_file(tmp_path)
    clock_values = [NOW]
    called: list[str] = []

    def fake_get(url: str, *, bounds: transport.PublicRequestBounds) -> bytes:
        transport.validate_public_request("GET", url, bounds=bounds)
        called.append(url)
        clock_values[0] += timedelta(seconds=2)
        if "yahoo" in url:
            return yahoo_payload(urlsplit(url).path.rsplit("/", 1)[1])
        return b"CURRENCY,TIME_PERIOD,OBS_VALUE\nUSD,2026-10-09,1.25\nKRW,2026-10-09,1750\n"

    output = tmp_path / "receipt"
    # When all four public payloads are collected.
    receipt = receipts.collect_receipt(
        output, calendar, clock=lambda: clock_values[0], fetch=fake_get
    )
    # Then receipt hashes refer to actual raw/normalized files and clocks bound response completion.
    assert receipt["failures"] == []
    assert [row["symbol"] for row in receipt["stocks"]] == ["CMCSA", "HIVE", "KDP"]
    assert receipt["kind"] == "P1_PUBLIC_DAILY" and receipt["schema_version"] == 1
    assert len(called) == 4
    for row in receipt["stocks"]:
        assert row["received_at"] is not None
        assert datetime.fromisoformat(row["received_at"]) > datetime.fromisoformat(
            row["request_started_at"]
        )
        assert row["events"]["splits"]
    assert receipt["created_at"] == clock_values[0].isoformat()
    assert (
        receipt["calendar_sha256"] == hashlib.sha256(calendar.read_bytes()).hexdigest()
    )
    for filename, digest in receipt["files"].items():
        assert hashlib.sha256((output / filename).read_bytes()).hexdigest() == digest
    with (output / "bars.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 6
    assert [(row["timestamp"], row["symbol"]) for row in rows] == sorted(
        (row["timestamp"], row["symbol"]) for row in rows
    )


def test_failed_payload_is_retained_and_other_symbols_still_available(tmp_path: Path):
    calendar = calendar_file(tmp_path)

    def fake_get(url: str, *, bounds: transport.PublicRequestBounds) -> bytes:
        if "HIVE" in url:
            return b"malformed"
        if "yahoo" in url:
            return yahoo_payload(urlsplit(url).path.rsplit("/", 1)[1])
        raise transport.PublicDataError("public_http_503")

    output = tmp_path / "receipt"
    receipt = receipts.collect_receipt(
        output, calendar, clock=lambda: NOW, fetch=fake_get
    )
    assert len(receipt["failures"]) == 2
    assert (output / "HIVE.yahoo.json").read_bytes() == b"malformed"
    assert "HIVE.yahoo.json" in receipt["files"]
    assert len((output / "bars.csv").read_text().splitlines()) == 5
    assert receipt["fx"]["received_at"] is None


def test_duplicate_calendar_and_existing_output_fail_before_wire(tmp_path: Path):
    with patch("nasdaq_auto_trader.research_public_transport.HTTPSConnection") as wire:
        with pytest.raises(transport.PublicDataError, match="calendar"):
            receipts.collect_receipt(
                tmp_path / "new",
                calendar_file(tmp_path, duplicate=True),
                clock=lambda: NOW,
            )
        output = tmp_path / "existing"
        output.mkdir()
        with pytest.raises(transport.PublicDataError, match="output"):
            receipts.collect_receipt(output, calendar_file(tmp_path), clock=lambda: NOW)
    wire.assert_not_called()


def test_explicit_calendar_excludes_incomplete_bars_and_rejects_non_session():
    sessions = {
        "2026-10-08": datetime(2026, 10, 8, 20, tzinfo=UTC),
        "2026-10-09": datetime(2026, 10, 9, 20, tzinfo=UTC),
    }
    data = parse_yahoo_daily(
        yahoo_payload("CMCSA"),
        "CMCSA",
        date(2026, 10, 8),
        date(2026, 10, 9),
        sessions=sessions,
        completed_at=NOW - timedelta(hours=2),
    )
    assert len(data.bars) == 1 and data.missing_dates == ()
    with pytest.raises(transport.PublicDataError, match="non_session"):
        parse_yahoo_daily(
            yahoo_payload("CMCSA", (10,)),
            "CMCSA",
            date(2026, 10, 8),
            date(2026, 10, 10),
            sessions=sessions,
            completed_at=NOW,
        )


def test_future_fx_dates_require_explicit_bounds():
    raw = b"CURRENCY,TIME_PERIOD,OBS_VALUE\nUSD,2026-10-09,1.25\nKRW,2026-10-09,1750\n"
    with pytest.raises(transport.PublicDataError):
        parse_ecb_fx(raw)
    assert parse_ecb_fx(raw, start=date(2026, 10, 1), end=NOW.date())[0].usdkrw == 1400


@pytest.mark.parametrize("events", [[], {"splits": {"bad": float("nan")}}])
def test_malformed_corporate_events_are_rejected_by_calendar_mode(events):
    document = json.loads(yahoo_payload("CMCSA"))
    document["chart"]["result"][0]["events"] = events
    sessions = {
        f"2026-10-{day:02}": datetime(2026, 10, day, 20, tzinfo=UTC) for day in (8, 9)
    }
    with pytest.raises(transport.PublicDataError):
        parse_yahoo_daily(
            json.dumps(document).encode(),
            "CMCSA",
            date(2026, 10, 8),
            NOW.date(),
            sessions=sessions,
            completed_at=NOW,
        )


def test_truncated_fx_payload_is_a_sanitized_collection_failure():
    with pytest.raises(transport.PublicDataError):
        parse_ecb_fx(
            b"CURRENCY,TIME_PERIOD,OBS_VALUE\nUSD,2026-10-09\n",
            start=date(2026, 10, 1),
            end=NOW.date(),
        )


def test_bounded_transport_keeps_no_redirect_size_and_retry_limits():
    bounds = transport.PublicRequestBounds(date(2026, 4, 1), NOW.date(), NOW)
    with patch.object(transport, "HTTPSConnection") as wire:
        wire.return_value.getresponse.return_value.status = 302
        with pytest.raises(transport.PublicDataError, match="redirect_denied"):
            transport.public_get(yahoo_url(), bounds=bounds)
        assert wire.call_count == 1
        assert wire.return_value.request.call_args.args[0] == "GET"
    with patch.object(transport, "HTTPSConnection") as wire:
        wire.return_value.getresponse.return_value.status = 200
        wire.return_value.getresponse.return_value.read.return_value = b"x" * 8_000_001
        with pytest.raises(transport.PublicDataError, match="response_too_large"):
            transport.public_get(yahoo_url(), bounds=bounds)
        wire.return_value.getresponse.return_value.read.assert_called_once_with(
            8_000_001
        )
    with (
        patch.object(transport, "HTTPSConnection", side_effect=OSError) as wire,
        patch.object(transport.time, "sleep"),
    ):
        with pytest.raises(transport.PublicDataError, match="transport_unavailable"):
            transport.public_get(yahoo_url(), bounds=bounds)
        assert wire.call_count == 2


def test_p1_cli_collect_publishes_offline_receipt_and_reports_failure(tmp_path: Path):
    module = receipts
    calendar = calendar_file(tmp_path)
    output = tmp_path / "cli-receipt"
    collect = module.collect_receipt

    def fake_get(url: str, *, bounds: transport.PublicRequestBounds) -> bytes:
        raise transport.PublicDataError("public_transport_unavailable")

    with patch.object(
        module,
        "collect_receipt",
        side_effect=lambda output, calendar: collect(
            output, calendar, clock=lambda: NOW, fetch=fake_get
        ),
    ):
        result = module.main(
            [
                "--p1-receipt",
                "--collect",
                "--output",
                str(output),
                "--calendar",
                str(calendar),
            ]
        )
    assert result == 1
    receipt = json.loads((output / "receipt.json").read_text())
    assert len(receipt["failures"]) == 4
    assert len((output / "bars.csv").read_text().splitlines()) == 1


@pytest.mark.parametrize("arguments,code", [(["--help"], 0), ([], 2)])
def test_p1_cli_help_and_missing_collect_do_not_fetch(arguments: list[str], code: int):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/collect_public_entry_data.py"),
            "--p1-receipt",
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == code
    assert "--collect" in result.stdout + result.stderr
