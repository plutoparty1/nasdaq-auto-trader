from __future__ import annotations

import json
import runpy
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from nasdaq_auto_trader.research_public_bars import exchange_close, parse_yahoo_daily
from nasdaq_auto_trader.research_public_fx import parse_ecb_fx
from nasdaq_auto_trader.research_public_transport import (
    PublicDataError,
    public_get,
    validate_public_request,
)


@pytest.mark.parametrize(
    "method,url",
    [
        ("POST", "https://query1.finance.yahoo.com/v8/finance/chart/CMCSA"),
        (
            "GET",
            "https://openapi.koreainvestment.com:9443/uapi/overseas-stock/v1/trading/order",
        ),
        ("GET", "https://query1.finance.yahoo.com/v8/finance/chart/CMCSA/../order"),
        ("GET", "https://query1.finance.yahoo.com@evil.example/v8/finance/chart/CMCSA"),
        ("GET", "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d"),
    ],
)
def test_public_transport_denies_non_allowlisted_requests(method, url):
    with pytest.raises(PublicDataError):
        validate_public_request(method, url)


def payload(close=10.0, duplicate=False):
    stamps = [int(datetime(2025, 3, 7, 14, 30, tzinfo=timezone.utc).timestamp())]
    if duplicate:
        stamps *= 2
    return json.dumps(
        {
            "chart": {
                "error": None,
                "result": [
                    {
                        "meta": {
                            "symbol": "CMCSA",
                            "currency": "USD",
                            "exchangeTimezoneName": "America/New_York",
                        },
                        "timestamp": stamps,
                        "indicators": {
                            "quote": [
                                {
                                    "open": [10.0] * len(stamps),
                                    "high": [11.0] * len(stamps),
                                    "low": [9.0] * len(stamps),
                                    "close": [close] * len(stamps),
                                    "volume": [100] * len(stamps),
                                }
                            ]
                        },
                    }
                ],
            }
        }
    ).encode()


@pytest.mark.parametrize(
    "content", [payload(close=-1), payload(close=float("nan")), payload(duplicate=True)]
)
def test_public_bars_reject_malformed_or_duplicate_data(content):
    with pytest.raises(PublicDataError):
        parse_yahoo_daily(content, "CMCSA", date(2024, 9, 1), date(2026, 9, 28))


def test_public_bars_keep_quote_prices_and_label_completed_close():
    result = parse_yahoo_daily(payload(), "CMCSA", date(2025, 3, 7), date(2025, 3, 7))
    assert result.bars[0].close == 10.0
    assert result.bars[0].timestamp == "2025-03-07T21:00:00+00:00"
    assert result.missing_dates == ()


@pytest.mark.parametrize(
    "day,expected",
    [
        (date(2025, 3, 10), "2025-03-10T20:00:00+00:00"),
        (date(2025, 7, 3), "2025-07-03T17:00:00+00:00"),
        (date(2024, 11, 29), "2024-11-29T18:00:00+00:00"),
        (date(2026, 7, 2), "2026-07-02T20:00:00+00:00"),
    ],
)
def test_public_timestamp_observes_dst_and_verified_early_closes(day, expected):
    assert exchange_close(day) == expected


def test_public_bars_exclude_outside_period_instead_of_using_future_bar():
    document = json.loads(payload())
    result = document["chart"]["result"][0]
    result["timestamp"].append(
        int(datetime(2026, 9, 29, 13, 30, tzinfo=timezone.utc).timestamp())
    )
    for values in result["indicators"]["quote"][0].values():
        values.append(values[0])
    data = parse_yahoo_daily(
        json.dumps(document).encode(), "CMCSA", date(2024, 9, 1), date(2026, 9, 28)
    )
    assert len(data.bars) == 1
    assert data.excluded_outside_period == 1


def test_public_fx_cross_uses_same_date_and_delayed_availability():
    result = parse_ecb_fx(
        b"CURRENCY,TIME_PERIOD,OBS_VALUE\nUSD,2024-08-30,1.25\nKRW,2024-08-30,1750\n"
    )
    assert result[0].usdkrw == 1400.0
    assert result[0].timestamp == "2024-08-30T16:00:00+00:00"


@pytest.mark.parametrize(
    "rows",
    [
        "USD,2024-08-30,1.25\n",
        "USD,2024-08-30,0\nKRW,2024-08-30,1400\n",
        "USD,2024-08-30,NaN\nKRW,2024-08-30,1400\n",
        "USD,2024-08-30,1\nUSD,2024-08-30,1\nKRW,2024-08-30,1400\n",
    ],
)
def test_public_fx_rejects_missing_invalid_and_duplicate_rates(rows):
    with pytest.raises(PublicDataError):
        parse_ecb_fx(("CURRENCY,TIME_PERIOD,OBS_VALUE\n" + rows).encode())


def test_public_requests_never_reach_wire_for_order_cancel_or_post():
    with patch(
        "nasdaq_auto_trader.research_public_transport.HTTPSConnection"
    ) as connection:
        with pytest.raises(PublicDataError):
            public_get(
                "https://openapi.koreainvestment.com:9443/uapi/overseas-stock/v1/trading/order-rvsecncl"
            )
        connection.assert_not_called()


def test_public_transport_does_not_follow_redirect():
    with patch(
        "nasdaq_auto_trader.research_public_transport.HTTPSConnection"
    ) as connection:
        connection.return_value.getresponse.return_value.status = 302
        with pytest.raises(PublicDataError, match="redirect_denied"):
            public_get(
                "https://data-api.ecb.europa.eu/service/data/EXR/D.USD+KRW.EUR.SP00.A?startPeriod=2024-08-30&endPeriod=2026-09-28&format=csvdata"
            )
        assert connection.call_count == 1
        assert connection.return_value.request.call_args.args[0] == "GET"


def test_public_transport_bounds_total_attempts():
    with (
        patch(
            "nasdaq_auto_trader.research_public_transport.HTTPSConnection",
            side_effect=OSError,
        ) as connection,
        patch("nasdaq_auto_trader.research_public_transport.time.sleep"),
        pytest.raises(PublicDataError, match="transport_unavailable"),
    ):
        public_get(
            "https://data-api.ecb.europa.eu/service/data/EXR/D.USD+KRW.EUR.SP00.A?startPeriod=2024-08-30&endPeriod=2026-09-28&format=csvdata"
        )
    assert connection.call_count == 2


def test_public_collector_preserves_nonempty_output_without_manifest(tmp_path):
    output = tmp_path / "existing-research"
    output.mkdir()
    sentinel = output / "CMCSA.csv"
    sentinel.write_bytes(b"existing-public-data-must-survive")
    script = (
        Path(__file__).resolve().parents[1] / "scripts/collect_public_entry_data.py"
    )
    with (
        patch.dict(sys.modules),
        patch.object(sys, "argv", [str(script), "--output", str(output)]),
        patch(
            "nasdaq_auto_trader.research_public_transport.HTTPSConnection",
            side_effect=AssertionError("network_must_not_start"),
        ) as wire,
        pytest.raises(SystemExit) as result,
    ):
        runpy.run_path(str(script), run_name="__main__")
    assert result.value.code == 2
    assert sentinel.read_bytes() == b"existing-public-data-must-survive"
    assert list(output.iterdir()) == [sentinel]
    wire.assert_not_called()
