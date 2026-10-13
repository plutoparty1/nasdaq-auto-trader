import json

import pytest

from nasdaq_auto_trader.research_readonly import (
    AUTH,
    DAILY,
    Credentials,
    Query,
    ReadOnlyKIS,
    ResearchError,
    WireRequest,
    WireResponse,
    https_wire,
    validate_query,
)


def credentials():
    return Credentials("test-key", "test-secret", "12345678", "01")


def daily():
    return Query(
        DAILY,
        "HHDFS76240000",
        {
            "AUTH": "",
            "EXCD": "NAS",
            "SYMB": "CMCSA",
            "GUBN": "0",
            "BYMD": "20260928",
            "MODP": "1",
        },
    )


@pytest.mark.parametrize(
    "path",
    [
        "/uapi/overseas-stock/v1/trading/order",
        "/uapi/overseas-stock/v1/trading/order-rvsecncl",
        "/uapi/hashkey",
        "/oauth2/revokeP",
        "https://attacker.invalid/oauth2/tokenP",
        "//attacker.invalid/x",
        DAILY + "/../order",
    ],
)
def test_forbidden_endpoint_never_reaches_wire(path):
    calls = []
    client = ReadOnlyKIS(
        credentials(), lambda request: calls.append(request), sleeper=lambda _: None
    )
    client.token = "test-token"
    with pytest.raises(ResearchError):
        client.get(Query(path, "HHDFS76240000", daily().params))
    assert calls == []
    with pytest.raises(ResearchError):
        https_wire(WireRequest("POST", path, {}, b"{}"))


@pytest.mark.parametrize(
    "key,value",
    [
        ("SYMB", "AAPL"),
        ("EXCD", "NYS"),
        ("MODP", "0"),
        ("BYMD", "2026-09-28"),
        ("AUTH", "x"),
    ],
)
def test_query_values_are_frozen(key, value):
    params = dict(daily().params)
    params[key] = value
    with pytest.raises(ResearchError):
        validate_query(Query(DAILY, "HHDFS76240000", params), credentials())


def test_tr_id_cannot_be_an_order_operation():
    with pytest.raises(ResearchError):
        validate_query(Query(DAILY, "TTTT1002U", daily().params), credentials())


def test_redirect_is_denied_without_followup():
    calls = []

    def wire(request):
        calls.append(request)
        return WireResponse(302, b"private content")

    client = ReadOnlyKIS(credentials(), wire, sleeper=lambda _: None)
    client.token = "test-token"
    with pytest.raises(ResearchError, match="redirect_denied"):
        client.get(daily())
    assert len(calls) == 1
    assert client.counts["order"] == client.counts["cancel"] == 0


def test_auth_is_single_post_and_token_not_persisted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []

    def wire(request):
        calls.append(request)
        return WireResponse(200, json.dumps({"access_token": "private-token"}).encode())

    client = ReadOnlyKIS(credentials(), wire, sleeper=lambda _: None)
    client.authenticate()
    assert [(x.method, x.path) for x in calls] == [("POST", AUTH)]
    assert list(tmp_path.iterdir()) == []
    assert "test-secret" not in repr(credentials())


def test_retry_has_two_attempt_ceiling_and_sanitized_error():
    calls = []

    def wire(request):
        calls.append(request)
        raise OSError("private token and account")

    client = ReadOnlyKIS(credentials(), wire, sleeper=lambda _: None)
    client.token = "test-token"
    with pytest.raises(ResearchError, match="^transport_unavailable$"):
        client.get(daily())
    assert len(calls) == 2
    assert client.counts["order"] == client.counts["cancel"] == 0


def test_api_rejection_does_not_expose_body():
    client = ReadOnlyKIS(
        credentials(),
        lambda _: WireResponse(200, b'{"rt_cd":"1","msg1":"private ledger"}'),
        sleeper=lambda _: None,
    )
    client.token = "test-token"
    with pytest.raises(ResearchError, match="^api_rejected$"):
        client.get(daily())


def test_credential_header_failure_is_sanitized():
    with pytest.raises(ResearchError, match="^credential_header_invalid$"):
        ReadOnlyKIS(Credentials("secret\r\nheader", "secret", "12345678", "01"))


def test_http_protocol_failure_is_sanitized():
    from http.client import HTTPException

    def wire(request):
        raise HTTPException("private response")

    client = ReadOnlyKIS(credentials(), wire, sleeper=lambda _: None)
    with pytest.raises(ResearchError, match="^transport_unavailable$"):
        client.authenticate()
    assert client.counts["auth"] == 1
