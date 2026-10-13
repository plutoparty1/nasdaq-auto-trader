from nasdaq_auto_trader.brokers.kis_client import KISCredentials
from nasdaq_auto_trader.brokers.kis_reconciliation import KISCancelOrder
from tests.test_kis_canary_reconciliation import FakeKISClient


def test_cancel_body_matches_official_cancel_contract() -> None:
    client = FakeKISClient(iter([{"output": {"ODNO": "original"}}]))
    client.cancel_order(KISCancelOrder("original", "AAPL", "buy", 1, 19.5))
    body = client.calls[0][4]
    assert body is not None
    assert body["OVRS_ORD_UNPR"] == "0"
    assert body["MGCO_APTM_ODNO"] == ""
    assert body["ORD_SVR_DVSN_CD"] == "0"


def test_cancel_acknowledges_separate_cancellation_order_number() -> None:
    client = FakeKISClient(iter([{"output": {"ODNO": "cancellation"}}]))
    result = client.cancel_order(KISCancelOrder("original", "AAPL", "buy", 1, 19.5))
    assert result.order_id == "original"
    assert result.cancellation_order_id == "cancellation"


def test_real_history_queries_all_symbols_with_wildcard() -> None:
    client = FakeKISClient(iter([{"output": []}]))
    client.credentials = KISCredentials("app", "secret", "12345678", paper=False)
    client.list_order_history("20260909", "20260909")
    params = client.calls[0][3]
    assert params is not None
    assert params["PDNO"] == "%"


def test_paper_history_uses_empty_exchange_for_all_orders() -> None:
    client = FakeKISClient(iter([{"output": []}]))
    client.list_order_history("20260909", "20260909")
    params = client.calls[0][3]
    assert params is not None
    assert params["OVRS_EXCG_CD"] == ""
