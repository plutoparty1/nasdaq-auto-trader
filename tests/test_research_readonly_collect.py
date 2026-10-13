import json

from nasdaq_auto_trader.research_readonly import Credentials, ReadOnlyKIS, WireResponse
from nasdaq_auto_trader.research_readonly_collect import daily, history
from nasdaq_auto_trader.research_readonly_minute import minute


def client_with(payload):
    client = ReadOnlyKIS(
        Credentials("fake", "fake", "12345678", "01"),
        lambda _: WireResponse(200, json.dumps(payload).encode()),
        sleeper=lambda _: None,
    )
    client.token = "fake"
    return client


def test_unfilled_order_is_not_a_fill_or_profit(tmp_path):
    client = client_with(
        {
            "output": [
                {
                    "ft_ord_qty": "1",
                    "ft_ccld_qty": "0",
                    "ft_ccld_unpr": "0",
                    "ord_tmd": "093000",
                }
            ]
        }
    )
    result = history(client, tmp_path)
    assert result["status_counts"]["filled"] == 0
    assert result["status_counts"]["accepted_or_unknown_unfilled"] == 1
    assert result["execution_time_status"] == "not_provided_in_observed_schema"
    assert result["roundtrip_holding_time_available"] is False
    assert client.counts["order"] == client.counts["cancel"] == 0


def test_daily_date_boundary_and_bad_ohlc(tmp_path):
    def row(day, close="10"):
        return {
            "xymd": day,
            "open": "10",
            "high": "11",
            "low": "9",
            "clos": close,
            "tvol": "100",
        }

    client = client_with(
        {"output2": [row("20260929"), row("20240929", "NaN"), row("20240928")]}
    )
    result = daily(client, tmp_path, "CMCSA")
    assert result["rows"] == 1
    assert result["invalid_ohlcv_rows"] == 1
    assert "2026-09-29" not in (tmp_path / "CMCSA-daily.csv").read_text()
    assert client.counts["order"] == client.counts["cancel"] == 0


def test_minute_collection_drives_normalizer_and_writes_only_private_rows(tmp_path):
    client = client_with(
        {
            "output2": [
                {
                    "xymd": "20260923",
                    "xhms": "093000",
                    "kymd": "20260923",
                    "khms": "223000",
                    "open": "10",
                    "high": "11",
                    "low": "9",
                    "last": "10.5",
                    "evol": "100",
                }
            ]
        }
    )
    result = minute(client, tmp_path, "CMCSA")
    assert result["status"] == "incident_start_reached"
    assert result["normalization"]["canonical_rows"] == 1
    assert (tmp_path / "CMCSA-5Min.csv").exists()
    assert client.counts["minute"] == 1
    assert client.counts["order"] == client.counts["cancel"] == 0
