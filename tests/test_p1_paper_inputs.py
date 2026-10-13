from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import pytest

from nasdaq_auto_trader.entry_comparison import load_entry_profile
from nasdaq_auto_trader.exit_experiment import candidates
from nasdaq_auto_trader.exit_experiment_config import ExperimentInputError
from nasdaq_auto_trader.p1_paper_inputs import read_receipt
from nasdaq_auto_trader.p1_paper_protocol import PaperProtocol, PaperSession, digest
from nasdaq_auto_trader.p1_public_receipt_types import Receipt
from nasdaq_auto_trader.p1_public_receipts import collect_receipt
from nasdaq_auto_trader.research_public_transport import (
    PublicRequestBounds,
    validate_public_request,
)

NOW = datetime(2026, 10, 9, 21, tzinfo=UTC)
FX_RAW = b"CURRENCY,TIME_PERIOD,OBS_VALUE\nUSD,2026-10-09,1\nKRW,2026-10-09,1350\n"


def receipt_fixture(
    tmp_path: Path, fx_raw: bytes = FX_RAW
) -> tuple[Path, PaperProtocol, Receipt]:
    calendar = tmp_path / "sessions.csv"
    _ = calendar.write_text(
        "session_date,open_at,close_at\n2026-10-09,2026-10-09T13:30:00+00:00,2026-10-09T20:00:00+00:00\n",
        encoding="utf-8",
    )

    def fake_get(url: str, *, bounds: PublicRequestBounds) -> bytes:
        validate_public_request("GET", url, bounds=bounds)
        if "yahoo" not in url:
            return fx_raw
        symbol = urlsplit(url).path.rsplit("/", 1)[1]
        quote = {
            key: [value]
            for key, value in {
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10,
                "volume": 100,
            }.items()
        }
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
                                int(NOW.replace(hour=13, minute=30).timestamp())
                            ],
                            "indicators": {"quote": [quote]},
                            "events": {},
                        }
                    ],
                }
            }
        ).encode()

    output = tmp_path / "receipt"
    metadata = collect_receipt(output, calendar, clock=lambda: NOW, fetch=fake_get)
    policy = next(item.policy for item in candidates() if item.name == "fixed_8")
    assert policy is not None
    protocol = PaperProtocol(
        tmp_path / "protocol.json",
        "synthetic",
        "2026-10-08T21:00:00+00:00",
        load_entry_profile(Path("experiments/entry_policy/profile.json")),
        policy,
        (
            PaperSession(
                "2026-10-09", "2026-10-09T13:30:00+00:00", "2026-10-09T20:00:00+00:00"
            ),
        ),
        {},
        {"calendar_sha256": digest(calendar)},
    )
    return output / "receipt.json", protocol, metadata


def write_metadata(path: Path, metadata: Receipt) -> None:
    _ = path.write_text(json.dumps(metadata), encoding="utf-8")


def test_valid_collector_receipt_loads_prices_fx_and_local_times(
    tmp_path: Path,
) -> None:
    path, protocol, _ = receipt_fixture(tmp_path)
    result = read_receipt(path, protocol, NOW)
    assert set(result.bars) == {"CMCSA", "HIVE", "KDP"}
    assert result.fx[0].usdkrw == 1350
    assert result.failures == ()
    assert result.fx_received_at == NOW.isoformat()


def test_null_response_duplicate_stock_is_rejected(tmp_path: Path) -> None:
    path, protocol, metadata = receipt_fixture(tmp_path)
    duplicate = copy.deepcopy(metadata["stocks"][0])
    duplicate["received_at"] = None
    duplicate["raw_sha256"] = None
    metadata["stocks"].insert(0, duplicate)
    write_metadata(path, metadata)
    with pytest.raises(ExperimentInputError):
        _ = read_receipt(path, protocol, NOW)


def test_receipt_requires_exact_three_stock_records(tmp_path: Path) -> None:
    path, protocol, metadata = receipt_fixture(tmp_path)
    metadata["stocks"] = [row for row in metadata["stocks"] if row["symbol"] != "HIVE"]
    bars = path.parent / "bars.csv"
    _ = bars.write_text(
        "\n".join(
            line
            for line in bars.read_text().splitlines()
            if not line.startswith("HIVE,")
        )
        + "\n"
    )
    metadata["files"]["bars.csv"] = digest(bars)
    write_metadata(path, metadata)
    with pytest.raises(ExperimentInputError):
        _ = read_receipt(path, protocol, NOW)


def test_fx_parse_failure_preserves_bars_for_protective_processing(
    tmp_path: Path,
) -> None:
    path, protocol, metadata = receipt_fixture(tmp_path, fx_raw=b"malformed")
    assert metadata["fx"]["received_at"] is not None
    result = read_receipt(path, protocol, NOW)
    assert result.fx == ()
    assert set(result.bars) == {"CMCSA", "HIVE", "KDP"}
    assert result.failures == tuple(metadata["failures"])
    assert result.fx_received_at == NOW.isoformat()


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw_sha256", "0" * 64),
        ("raw_file", "HIVE.yahoo.json"),
        ("request_started_at", "2026-10-09T20:59:00+00:00"),
        ("source", "https://example.com/CMCSA"),
    ],
)
def test_stock_metadata_must_match_raw_file_and_clock_lineage(
    tmp_path: Path,
    field: Literal["raw_sha256", "raw_file", "request_started_at", "source"],
    value: str,
) -> None:
    path, protocol, metadata = receipt_fixture(tmp_path)
    metadata["stocks"][0][field] = value
    write_metadata(path, metadata)
    with pytest.raises(ExperimentInputError):
        _ = read_receipt(path, protocol, NOW)


@pytest.mark.parametrize(
    "stamp", ["2026-10-09T20:59:00+00:00", "2026-10-09T21:01:00+00:00"]
)
def test_created_at_must_bound_responses_and_evaluation_time(
    tmp_path: Path, stamp: str
) -> None:
    path, protocol, metadata = receipt_fixture(tmp_path)
    metadata["created_at"] = stamp
    write_metadata(path, metadata)
    with pytest.raises(ExperimentInputError):
        _ = read_receipt(path, protocol, NOW)


def test_missing_fx_failure_cannot_explain_empty_normalized_fx(tmp_path: Path) -> None:
    path, protocol, metadata = receipt_fixture(tmp_path, fx_raw=b"malformed")
    metadata["failures"] = []
    write_metadata(path, metadata)
    with pytest.raises(ExperimentInputError):
        _ = read_receipt(path, protocol, NOW)


def test_exact_three_records_still_reject_duplicate_null_responses(
    tmp_path: Path,
) -> None:
    path, protocol, metadata = receipt_fixture(tmp_path)
    failed = copy.deepcopy(metadata["stocks"][0])
    failed["received_at"] = None
    failed["raw_sha256"] = None
    metadata["stocks"] = [failed, copy.deepcopy(failed), metadata["stocks"][2]]
    del metadata["files"]["CMCSA.yahoo.json"]
    metadata["failures"] = ["CMCSA:public_transport_unavailable"]
    write_metadata(path, metadata)
    with pytest.raises(ExperimentInputError, match="duplicate"):
        _ = read_receipt(path, protocol, NOW)


def test_failed_stock_keeps_other_normalized_prices_available(tmp_path: Path) -> None:
    path, protocol, metadata = receipt_fixture(tmp_path)
    failed = metadata["stocks"][1]
    failed["received_at"] = None
    failed["raw_sha256"] = None
    del metadata["files"]["HIVE.yahoo.json"]
    metadata["failures"] = ["HIVE.yahoo.json:public_transport_unavailable"]
    bars = path.parent / "bars.csv"
    _ = bars.write_text(
        "\n".join(
            line
            for line in bars.read_text().splitlines()
            if not line.startswith("HIVE,")
        )
        + "\n"
    )
    metadata["files"]["bars.csv"] = digest(bars)
    write_metadata(path, metadata)
    result = read_receipt(path, protocol, NOW)
    assert set(result.bars) == {"CMCSA", "KDP"}
    assert "HIVE" not in result.received_at
    assert result.failures == tuple(metadata["failures"])


def test_nonempty_invalid_fx_is_not_ignored_when_failure_is_present(
    tmp_path: Path,
) -> None:
    path, protocol, metadata = receipt_fixture(tmp_path)
    fx = path.parent / "usdkrw.csv"
    _ = fx.write_text("timestamp,usdkrw\n2026-10-09T16:00:00+00:00,-1\n")
    metadata["files"]["usdkrw.csv"] = digest(fx)
    metadata["failures"] = ["ECB:public_fx_invalid"]
    write_metadata(path, metadata)
    with pytest.raises(ExperimentInputError):
        _ = read_receipt(path, protocol, NOW)


def test_fx_response_hash_must_match_manifest(tmp_path: Path) -> None:
    path, protocol, metadata = receipt_fixture(tmp_path)
    metadata["fx"]["raw_sha256"] = "0" * 64
    write_metadata(path, metadata)
    with pytest.raises(ExperimentInputError, match="raw_hash"):
        _ = read_receipt(path, protocol, NOW)
