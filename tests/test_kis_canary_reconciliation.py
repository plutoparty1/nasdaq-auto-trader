from __future__ import annotations

from collections.abc import Iterator

import pytest

from nasdaq_auto_trader.brokers.common import BrokerRequestError, JsonObject
from nasdaq_auto_trader.brokers.kis_client import KISClient, KISCredentials
from nasdaq_auto_trader.brokers.kis_reconciliation import KISCancelOrder


class FakeKISClient(KISClient):
    def __init__(self, responses: Iterator[JsonObject]) -> None:
        super().__init__(KISCredentials("app", "secret", "12345678"))
        self.responses = responses
        self.calls: list[tuple[str, str, str, dict[str, str] | None, JsonObject | None]] = []

    def _request(
        self,
        method: str,
        path: str,
        tr_id: str,
        params: dict[str, str] | None = None,
        body: JsonObject | None = None,
        tr_cont: str = "",
    ) -> JsonObject:
        self.calls.append((method, path, tr_id, params, body))
        response = next(self.responses)
        self._last_tr_cont = str(response.get("_test_tr_cont", ""))
        return response


def _client(*responses: JsonObject) -> FakeKISClient:
    return FakeKISClient(iter(responses))


def test_list_open_orders_parses_kis_nccs_row() -> None:
    client = _client({"output1": [{
        "odno": "9001",
        "pdno": "AAPL",
        "sll_buy_dvsn_cd": "02",
        "ft_ord_qty": "3",
        "ft_ccld_qty": "1",
        "ft_ord_unpr3": "19.50",
    }]})

    orders = client.list_open_orders()

    assert orders[0].order_id == "9001"
    assert orders[0].symbol == "AAPL"
    assert orders[0].side == "buy"
    assert orders[0].remaining_quantity == 2
    assert client.calls[0][1:] == (
        "/uapi/overseas-stock/v1/trading/inquire-nccs",
        "VTTS3018R",
        client.calls[0][3],
        None,
    )
    assert client.calls[0][3]["CANO"] == "12345678"
    assert client.calls[0][3]["ACNT_PRDT_CD"] == "01"
    assert client.calls[0][3]["OVRS_EXCG_CD"] == "NASD"
    assert client.calls[0][3]["SORT_SQN"] == "DS"


def test_official_output_shape_and_history_parameters_are_supported() -> None:
    client = _client({"output": []})

    history = client.list_order_history("20260717", "20260717")

    assert history == ()
    params = client.calls[0][3]
    assert params is not None
    assert params["CANO"] == "12345678"
    assert params["ACNT_PRDT_CD"] == "01"
    assert params["ORD_STRT_DT"] == "20260717"
    assert params["ORD_END_DT"] == "20260717"
    assert params["CCLD_NCCS_DVSN"] == "00"


def test_list_order_history_parses_filled_row() -> None:
    client = _client({"output1": [{
        "odno": "9002",
        "pdno": "MSFT",
        "sll_buy_dvsn_cd": "01",
        "ft_ord_qty": "2",
        "ft_ccld_qty": "2",
        "ft_ccld_unpr": "18.25",
        "ord_dt": "20260717",
        "ord_tmd": "101500",
    }]})

    history = client.list_order_history("20260717", "20260717")

    assert history[0].order_id == "9002"
    assert history[0].side == "sell"
    assert history[0].filled_quantity == 2
    assert history[0].average_fill_price == 18.25


def test_cancel_order_uses_original_order_number_once() -> None:
    client = _client({"output": {"ODNO": "9001"}})

    result = client.cancel_order(KISCancelOrder("9001", "AAPL", "buy", 2, 19.5))

    assert result.order_id == "9001"
    assert len(client.calls) == 1
    assert client.calls[0][0] == "POST"
    assert client.calls[0][2] == "VTTT1004U"
    assert client.calls[0][4] == {
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "OVRS_EXCG_CD": "NASD",
        "PDNO": "AAPL",
        "ORGN_ODNO": "9001",
        "RVSE_CNCL_DVSN_CD": "02",
        "ORD_QTY": "2",
        "OVRS_ORD_UNPR": "0",
        "MGCO_APTM_ODNO": "",
        "ORD_SVR_DVSN_CD": "0",
    }


def test_ambiguous_cancel_response_requires_reconciliation() -> None:
    client = _client({"output": {"msg": "accepted"}})

    with pytest.raises(BrokerRequestError, match="cancel_order_number_missing"):
        client.cancel_order(KISCancelOrder("9001", "AAPL", "buy", 2, 19.5))

    assert len(client.calls) == 1


def test_cancel_order_rejects_lowercase_order_number_field() -> None:
    client = _client({"output": {"odno": "9001"}})

    with pytest.raises(BrokerRequestError, match="cancel_order_number_missing"):
        client.cancel_order(KISCancelOrder("9001", "AAPL", "buy", 2, 19.5))


def test_balance_open_orders_and_history_follow_all_continuation_pages() -> None:
    client = _client(
        {"output1": [{"odno": "1", "pdno": "AAPL", "sll_buy_dvsn_cd": "02", "ft_ord_qty": "1", "ft_ccld_qty": "0", "ft_ord_unpr3": "10"}], "tr_cont": "M", "ctx_area_nk200": "next"},
        {"output1": [{"odno": "2", "pdno": "MSFT", "sll_buy_dvsn_cd": "01", "ft_ord_qty": "1", "ft_ccld_qty": "0", "ft_ord_unpr3": "11"}]},
        {"output1": [{"odno": "3", "pdno": "AAPL", "sll_buy_dvsn_cd": "02", "ft_ord_qty": "1", "ft_ccld_qty": "1", "ft_ccld_unpr": "12"}], "_test_tr_cont": "M", "ctx_area_nk200": "history-next"},
        {"output1": [{"odno": "4", "pdno": "MSFT", "sll_buy_dvsn_cd": "01", "ft_ord_qty": "1", "ft_ccld_qty": "1", "ft_ccld_unpr": "13"}]},
    )

    assert [order.order_id for order in client.list_open_orders()] == ["1", "2"]
    assert [order.order_id for order in client.list_order_history("20260717", "20260717")] == ["3", "4"]
    assert [call[3]["CTX_AREA_NK200"] for call in client.calls] == ["", "next", "", "history-next"]


def test_repeated_or_failed_continuation_page_fails_closed() -> None:
    repeated = _client(
        {"output1": [], "tr_cont": "M", "ctx_area_nk200": "same"},
        {"output1": [], "tr_cont": "M", "ctx_area_nk200": "same"},
    )
    with pytest.raises(BrokerRequestError, match="continuation_repeated"):
        repeated.list_open_orders()

    malformed = _client({"output1": [{"odno": "missing-fields"}]})
    with pytest.raises(BrokerRequestError, match="open_order_row_invalid"):
        malformed.list_open_orders()


@pytest.mark.parametrize("method", ["open_orders", "history"])
def test_missing_reconciliation_rows_never_mean_empty_state(method: str) -> None:
    client = _client({"rt_cd": "0"})

    with pytest.raises(BrokerRequestError, match="kis_reconciliation_rows_missing"):
        if method == "open_orders":
            client.list_open_orders()
        else:
            client.list_order_history("20260717", "20260717")


def test_trade_volume_universe_preserves_rank_and_caps_at_ten() -> None:
    rows = [{"symb": f"S{i:02d}", "last": "19.50"} for i in range(30)]
    client = _client({"output2": rows})

    result = client.get_trade_volume_universe({f"S{i:02d}" for i in range(30)})

    assert result == tuple(f"S{i:02d}" for i in range(10))


@pytest.mark.parametrize("rows", [
    [{"symb": "AAPL", "last": "not-a-number"}],
    [{"symb": "AAPL", "last": "19.50"}, {"symb": "AAPL", "last": "19.40"}],
])
def test_trade_volume_malformed_or_duplicate_rows_fail_closed(rows: list[JsonObject]) -> None:
    client = _client({"output2": rows})

    with pytest.raises(BrokerRequestError):
        client.get_trade_volume_universe({"AAPL"})


def test_trade_volume_validates_rows_after_the_ten_result_cap() -> None:
    rows = [{"symb": f"S{i:02d}", "last": "19.50"} for i in range(10)]
    rows.append({"symb": "S00", "last": "19.40"})
    client = _client({"output2": rows})

    with pytest.raises(BrokerRequestError, match="duplicate"):
        client.get_trade_volume_universe({f"S{i:02d}" for i in range(10)})
