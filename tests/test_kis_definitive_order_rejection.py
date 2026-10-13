import json
from io import BytesIO
from pathlib import Path
from typing import Final
from urllib.error import HTTPError
from urllib.request import Request
from urllib.response import addinfourl

import pytest

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditEvent, NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.brokers.kis_client import KISClient, KISCredentials
from nasdaq_auto_trader.brokers.kis_reconciliation import KISOpenOrder
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, Position
from nasdaq_auto_trader.session_claims import ClaimStatus, SignalKey
from nasdaq_auto_trader.trading_session_store import (
    SafetyReservationRequest,
    TradingSessionStore,
)
from tests.auto_symbol_live_guard_fixtures import _live_engine, _write_champion

ORDER_PATH: Final = "/uapi/overseas-stock/v1/trading/order"
REJECTION_MESSAGE: Final = "주문 가격을 확인 하시기 바랍니다. 1$이상 소수점 2자리까지만 가능 합니다."
REJECTION: Final = json.dumps({
    "rt_cd": "1", "msg_cd": "APBK0956", "msg1": REJECTION_MESSAGE,
}, ensure_ascii=False, separators=(",", ":")).encode()


class OrderClient(KISClient):
    def _ensure_token(self) -> None:
        self._access_token = "test-token"

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        return AccountSnapshot(10_000, 10_000, 10_000)

    def get_overseas_buying_power(
        self, symbol: str, order_price: float | None = None,
    ) -> float:
        return 10_000.0

    def list_open_orders(self) -> tuple[KISOpenOrder, ...]:
        return ()

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        return {}

    def get_latest_price(self, symbol: str) -> float:
        return 239.0


def make_engine(tmp_path: Path, audit: NullAuditLogger) -> TradingEngine:
    paths = StrategyArtifactPaths.from_root(tmp_path / "artifacts")
    _write_champion(paths)
    broker = OrderClient(KISCredentials("app", "secret", "12345678"))
    store = TradingSessionStore(tmp_path / "session.json")
    return _live_engine(paths, AutomaticOrderGuard(paths, store, audit), broker)


def response(body: bytes = REJECTION, status: int = 200) -> addinfourl:
    return addinfourl(BytesIO(body), {}, "https://example.test" + ORDER_PATH, status)


def next_reservation(store: TradingSessionStore, symbol: str) -> bool:
    key = SignalKey("2026-07-13", "auto", "v1", symbol, "buy", "next-signal")
    request = SafetyReservationRequest(
        "2026-07-13", "buy", "2026-07-13T14:40:00+00:00",
        0, 0, 0, False, False, True, 0,
    )
    return store.claim_and_reserve_safety(key, request).granted


def test_broker_business_rejection_is_finalized_before_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a real KIS adapter receiving a complete rejected order response.
    audit = NullAuditLogger()
    engine = make_engine(tmp_path, audit)
    sent: list[Request] = []

    def reject(request: Request, *, timeout: float) -> addinfourl:
        assert request.get_method() == "POST" and request.full_url.endswith(ORDER_PATH)
        sent.append(request)
        return response()

    monkeypatch.setattr("nasdaq_auto_trader.brokers.kis_auth.urlopen", reject)
    # When the automatic engine submits and a fresh store recovers interrupted claims.
    results = engine.run_once()
    reopened = TradingSessionStore(tmp_path / "session.json")
    recovered = reopened.recover_interrupted_claims()
    # Then rejection is durable, the broker code survives, and a new signal can proceed.
    assert len(sent) == 1
    assert results[0]["response"]["broker_response"] == {
        "status": "rejected", "msg_cd": "APBK0956",
    }
    assert recovered == 0
    symbol = results[0]["symbol"]
    assert reopened.claim(SignalKey(
        "2026-07-13", "auto", "v1", symbol, "buy", "2026-07-13T14:29:00+00:00",
    )).status is ClaimStatus.REJECTED
    assert next_reservation(reopened, symbol)
    assert audit.events[-1].payload["broker_submitted"] is False


@pytest.mark.parametrize("failure", [TimeoutError("response lost"), BrokerRequestError("unknown outcome")])
def test_ambiguous_transport_failure_remains_uncertain_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    failure: TimeoutError | BrokerRequestError,
) -> None:
    # Given an order whose transport cannot establish broker acceptance.
    engine = make_engine(tmp_path, NullAuditLogger())

    def fail(request: Request, *, timeout: float) -> addinfourl:
        raise failure

    monkeypatch.setattr("nasdaq_auto_trader.brokers.kis_auth.urlopen", fail)
    # When submission fails and the session restarts.
    with pytest.raises(type(failure)):
        engine.run_once()
    reopened = TradingSessionStore(tmp_path / "session.json")
    # Then the durable uncertain gate still prevents a later signal.
    assert reopened.recover_interrupted_claims() == 1
    assert not next_reservation(reopened, "AAPL")


@pytest.mark.parametrize("body", [
    REJECTION[:-1] + b',"output":{"ODNO":"123"}}',
    REJECTION[:-1] + b',"output":[{"odno":"123"}]}',
    REJECTION[:-1] + b',"id":"123"}',
    REJECTION.replace(b'APBK0956', b''),
    REJECTION.replace(b'APBK0956', b'EGW00201'),
    REJECTION.replace(b'APBK0956', b' EGW00201'),
    REJECTION.replace(b'APBK0956', b'unknown code'),
    REJECTION.replace(b'"rt_cd":"1"', b'"rt_cd":"2"'),
    pytest.param(REJECTION.replace(REJECTION_MESSAGE.encode(), b'Unknown processing failure'),
                 id="unknown-business-error"),
])
def test_ambiguous_broker_failure_payload_remains_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: bytes,
) -> None:
    engine = make_engine(tmp_path, NullAuditLogger())
    monkeypatch.setattr("nasdaq_auto_trader.brokers.kis_auth.urlopen", lambda *args, **kwargs: response(body))
    with pytest.raises(BrokerRequestError):
        engine.run_once()
    reopened = TradingSessionStore(tmp_path / "session.json")
    assert reopened.recover_interrupted_claims() == 1
    assert not next_reservation(reopened, "AAPL")


def test_rejection_audit_failure_keeps_terminal_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = NullAuditLogger()
    engine = make_engine(tmp_path, audit)

    def write_intent_only(event: AuditEvent) -> bool:
        return event.event_type != "automatic_order_blocked"

    monkeypatch.setattr(audit, "append", write_intent_only)
    monkeypatch.setattr("nasdaq_auto_trader.brokers.kis_auth.urlopen", lambda *args, **kwargs: response())
    result = engine.run_once()[0]["response"]
    assert result["terminal"] is True
    assert result["reason"] == "order_outcome_audit_failed_reconcile_required"
    reopened = TradingSessionStore(tmp_path / "session.json")
    assert reopened.recover_interrupted_claims() == 0
    assert not next_reservation(reopened, "AAPL")


@pytest.mark.parametrize("method,path", [
    ("GET", ORDER_PATH), ("POST", "/oauth2/tokenP"), ("POST", ORDER_PATH + "-rvsecncl"),
])
def test_non_order_requests_keep_generic_broker_failure(
    monkeypatch: pytest.MonkeyPatch, method: str, path: str,
) -> None:
    client = OrderClient(KISCredentials("app", "secret", "12345678"))
    monkeypatch.setattr("nasdaq_auto_trader.brokers.kis_auth.urlopen", lambda *args, **kwargs: response())
    with pytest.raises(BrokerRequestError) as raised:
        client._open_json(Request("https://example.test" + path, method=method), "KIS API")
    assert type(raised.value) is BrokerRequestError


def test_non_200_response_keeps_generic_broker_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OrderClient(KISCredentials("app", "secret", "12345678"))
    monkeypatch.setattr("nasdaq_auto_trader.brokers.kis_auth.urlopen", lambda *args, **kwargs: response(status=201))
    with pytest.raises(BrokerRequestError) as raised:
        client._open_json(Request("https://example.test" + ORDER_PATH, method="POST"), "KIS API")
    assert type(raised.value) is BrokerRequestError


def test_http_error_with_rejection_body_remains_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = make_engine(tmp_path, NullAuditLogger())

    def fail(request: Request, *, timeout: float) -> addinfourl:
        raise HTTPError(request.full_url, 503, "unavailable", {}, BytesIO(REJECTION))

    monkeypatch.setattr("nasdaq_auto_trader.brokers.kis_auth.urlopen", fail)
    with pytest.raises(BrokerRequestError):
        engine.run_once()
    reopened = TradingSessionStore(tmp_path / "session.json")
    assert reopened.recover_interrupted_claims() == 1
    assert not next_reservation(reopened, "AAPL")
