from __future__ import annotations

from collections.abc import Iterator

import pytest

from nasdaq_auto_trader.brokers.common import BrokerRequestError, JsonObject
from nasdaq_auto_trader.brokers.kis_client import KISClient, KISCredentials


class BalancePagesClient(KISClient):
    def __init__(self, responses: Iterator[JsonObject]) -> None:
        super().__init__(KISCredentials("app", "secret", "12345678"))
        self.responses = responses
        self.continuations: list[str] = []

    def _request(
        self,
        method: str,
        path: str,
        tr_id: str,
        params: dict[str, str] | None = None,
        body: JsonObject | None = None,
        tr_cont: str = "",
        deadline: float | None = None,
    ) -> JsonObject:
        del method, path, tr_id, body, deadline
        self.continuations.append((params or {})["CTX_AREA_NK200"])
        return next(self.responses)


def test_balance_positions_follow_all_continuation_pages() -> None:
    client = BalancePagesClient(
        iter(
            (
                {
                    "output1": [_position("AAPL")],
                    "tr_cont": "M",
                    "ctx_area_nk200": "next",
                },
                {"output1": [_position("MSFT")]},
            )
        )
    )

    positions = client.list_positions(refresh=True)

    assert tuple(positions) == ("AAPL", "MSFT")
    assert client.continuations == ["", "next"]


def test_balance_repeated_continuation_fails_closed() -> None:
    client = BalancePagesClient(
        iter(
            (
                {"output1": [], "tr_cont": "M", "ctx_area_nk200": "same"},
                {"output1": [], "tr_cont": "M", "ctx_area_nk200": "same"},
            )
        )
    )

    with pytest.raises(BrokerRequestError, match="balance_continuation_repeated"):
        client.list_positions(refresh=True)


def test_balance_duplicate_position_across_pages_fails_closed() -> None:
    client = BalancePagesClient(
        iter(
            (
                {
                    "output1": [_position("AAPL")],
                    "tr_cont": "M",
                    "ctx_area_nk200": "next",
                },
                {"output1": [_position("AAPL")]},
            )
        )
    )

    with pytest.raises(BrokerRequestError, match="balance_position_duplicate"):
        client.list_positions(refresh=True)


@pytest.mark.parametrize(
    "payload,reason",
    [
        ({}, "balance_position_rows_missing"),
        (
            {"output1": [{"ovrs_pdno": "AAPL", "ovrs_cblc_qty": "unknown"}]},
            "balance_position_quantity_invalid",
        ),
    ],
)
def test_malformed_balance_payload_never_means_no_positions(
    payload: JsonObject,
    reason: str,
) -> None:
    client = BalancePagesClient(iter((payload,)))

    with pytest.raises(BrokerRequestError, match=reason):
        client.list_positions(refresh=True)


def _position(symbol: str) -> JsonObject:
    return {
        "ovrs_pdno": symbol,
        "ovrs_cblc_qty": "1",
        "ovrs_stck_evlu_amt": "19.00",
        "pchs_avg_pric": "18.00",
    }
