from datetime import UTC, datetime

import pytest

from nasdaq_auto_trader.brokers.common import JsonObject
from nasdaq_auto_trader.brokers.kis_reconciliation import KISOrderHistory
from tests.test_kis_canary_reconciliation import FakeKISClient


def _row(**changes: str) -> JsonObject:
    return {
        "odno": "9001", "orgn_odno": "0000000000", "pdno": "AAPL",
        "sll_buy_dvsn_cd": "02", "ft_ord_qty": "3", "ft_ccld_qty": "0",
        "ft_ccld_unpr3": "0", "rvse_cncl_dvsn": "00",
        "prcs_stat_name": "완료", "ord_dt": "20260918",
        "ord_tmd": "103000", "ovrs_excg_cd": "NASD", **changes,
    }


def _cancel(**changes: str) -> JsonObject:
    return _row(odno="9002", orgn_odno="9001", rvse_cncl_dvsn="02", **changes)


def _history(*rows: JsonObject) -> tuple[KISOrderHistory, ...]:
    client = FakeKISClient(iter([{"output": list(rows)}]))
    return client.list_order_history("20260918", "20260918")


@pytest.mark.parametrize("filled,canceled", [("0", "3"), ("1", "2")])
def test_original_is_canceled_when_completed_cancel_accounts_for_remaining_quantity(
    filled: str, canceled: str,
) -> None:
    # Given a completed cancellation linked to its original order.
    original = _row(ft_ccld_qty=filled, ft_ccld_unpr3="19" if filled == "1" else "0")
    # When the real adapter consumes the raw KIS response.
    history = _history(original, _cancel(ft_ord_qty=canceled))
    # Then only the original order gains cancellation finality.
    assert history[0].status == "canceled"
    assert history[1].status == "unknown"


@pytest.mark.parametrize("changes", [
    {"prcs_stat_name": "전송"}, {"prcs_stat_name": "거부"},
    {"prcs_stat_name": "취소완료"}, {"ft_ord_qty": "2"},
    {"ft_ord_qty": "4"}, {"ft_ccld_qty": "1"},
    {"pdno": "MSFT"}, {"sll_buy_dvsn_cd": "01"},
    {"ord_dt": "20260917"}, {"ovrs_excg_cd": "NYSE"},
    {"rvse_cncl_dvsn": "01"}, {"orgn_odno": "unmatched"},
])
def test_original_stays_unknown_when_cancel_evidence_is_incomplete(changes: dict[str, str]) -> None:
    # Given a child row without an exact completed full-cancel contract.
    child = {**_cancel(), **changes}
    # When the raw rows are reconciled.
    history = _history(_row(), child)
    # Then a pending receipt cannot be released.
    assert history[0].status == "unknown"


def test_original_stays_unknown_when_cancellation_rows_are_duplicated() -> None:
    # Given duplicated cancellation evidence.
    rows = (_row(), _cancel(), _cancel())
    # When the adapter reads it.
    history = _history(*rows)
    # Then duplicate quantities never prove finality.
    assert history[0].status == "unknown"


@pytest.mark.parametrize("extra", [
    _row(), _row(odno="9003", orgn_odno="9001", rvse_cncl_dvsn="01"),
])
def test_original_stays_unknown_when_order_identity_or_amendment_is_ambiguous(
    extra: JsonObject,
) -> None:
    history = _history(_row(), _cancel(), extra)
    assert history[0].status == "unknown"


@pytest.mark.parametrize("kind", ["01", "02"])
@pytest.mark.parametrize("state", ["전송", "완료", "거부"])
def test_amend_cancel_requests_are_not_original_executions(kind: str, state: str) -> None:
    history = _history(_row(
        orgn_odno="8000", rvse_cncl_dvsn=kind, prcs_stat_name=state,
        ft_ccld_qty="3", ft_ccld_unpr3="19",
    ))
    assert history[0].is_original_order is False
    assert history[0].status == "unknown"
    assert history[0].filled_quantity == 3


def test_full_cancellation_can_be_confirmed_across_history_pages() -> None:
    client = FakeKISClient(iter([
        {"output": [_row()], "tr_cont": "M", "ctx_area_nk200": "next"},
        {"output": [_cancel()]},
    ]))
    history = client.list_order_history("20260918", "20260918")
    assert history[0].status == "canceled"
    assert history[0].is_original_order is True


@pytest.mark.parametrize("changes,expected", [
    ({"prcs_stat_name": "거부"}, "rejected"),
    ({"ft_ccld_qty": "3", "ft_ccld_unpr3": "19"}, "filled"),
    ({"nccs_qty": "0"}, "unknown"),
    ({"prcs_stat_name": "취소접수"}, "unknown"),
    ({"prcs_stat_name": "완료(취소)"}, "unknown"),
    ({"prcs_stat_name": "만료"}, "unknown"),
])
def test_status_uses_documented_exact_processing_values(
    changes: dict[str, str], expected: str,
) -> None:
    # Given a raw original order with the specified processing evidence.
    row = {**_row(), **changes}
    # When it crosses the adapter boundary.
    history = _history(row)
    # Then unsupported labels and zero remaining quantity stay unknown.
    assert history[0].status == expected


@pytest.mark.parametrize("changes,expected", [
    ({}, datetime(2026, 9, 18, 14, 30, tzinfo=UTC)),
    ({"ord_dt": "20260116"}, datetime(2026, 1, 16, 15, 30, tzinfo=UTC)),
    ({"ord_tmd": ""}, None),
    ({"ord_dt": "20260230"}, None),
    ({"ord_tmd": "246000"}, None),
    ({"ovrs_excg_cd": "SEHK"}, None),
    ({"ord_dt": "20261101", "ord_tmd": "013000"}, None),
    ({"ord_dt": "20260308", "ord_tmd": "023000"}, None),
])
def test_submission_time_uses_exchange_local_reception_time(
    changes: dict[str, str], expected: datetime | None,
) -> None:
    # Given the documented local reception date/time and exchange.
    row = {**_row(), **changes}
    # When the adapter constructs the history item.
    history = _history(row)
    # Then ordering uses an aware instant, or none for ambiguous evidence.
    assert history[0].submitted_at == expected
