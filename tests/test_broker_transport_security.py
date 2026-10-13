from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest

from nasdaq_auto_trader.brokers.alpaca import AlpacaClient, AlpacaCredentials
from nasdaq_auto_trader.brokers.common import BrokerRequestError, JsonObject
from nasdaq_auto_trader.brokers.kis_client import KISClient, KISCredentials


@dataclass(frozen=True, slots=True)
class LocalBrokerEndpoint:
    base_url: str
    requests: list[str]


@pytest.fixture
def endpoint() -> Iterator[LocalBrokerEndpoint]:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append(self.path)
            if self.path == "/error":
                self.send_response(401)
                self.end_headers()
                self.wfile.write(
                    b'{"msg_cd":"DUMMY_AUTH_FAILURE","appsecret":"synthetic-secret"}'
                )
                return
            if self.path.startswith("/redirect/"):
                self.send_response(int(self.path.rsplit("/", 1)[1]))
                self.send_header(
                    "Location", f"http://localhost:{server.server_port}/target"
                )
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield LocalBrokerEndpoint(
                f"http://127.0.0.1:{server.server_port}", requests
            )
        finally:
            server.shutdown()
            worker.join(timeout=2)


@pytest.fixture(params=("kis", "alpaca"))
def broker_get(
    request: pytest.FixtureRequest,
    endpoint: LocalBrokerEndpoint,
    tmp_path: Path,
) -> Callable[[str], JsonObject]:
    if request.param == "kis":
        kis = KISClient(
            KISCredentials("dummy-key", "dummy-secret", "12345678"),
            token_cache_path=tmp_path / "cache.json",
        )
        kis.base_url = endpoint.base_url
        kis._access_token = "dummy-token"
        kis._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        return lambda path: kis._request("GET", path, "DUMMY")
    alpaca = AlpacaClient(AlpacaCredentials("dummy-key", "dummy-secret"))
    return lambda path: alpaca._request("GET", endpoint.base_url, path)


@pytest.mark.parametrize("status", (301, 302, 303, 307, 308))
def test_broker_rejects_redirect_before_sending_credentials_to_another_origin(
    endpoint: LocalBrokerEndpoint,
    broker_get: Callable[[str], JsonObject],
    status: int,
) -> None:
    # Given a broker endpoint redirecting to a different hostname.
    path = f"/redirect/{status}"

    # When the real broker transport receives the redirect.
    with pytest.raises(BrokerRequestError):
        broker_get(path)

    # Then only the original endpoint was contacted.
    assert endpoint.requests == [path]


def test_broker_decodes_successful_response_without_redirect(
    endpoint: LocalBrokerEndpoint,
    broker_get: Callable[[str], JsonObject],
) -> None:
    # Given a directly responding broker endpoint.
    # When the real broker transport requests JSON.
    result = broker_get("/success")

    # Then existing successful request behavior is preserved.
    assert result == {"ok": True}
    assert endpoint.requests == ["/success"]


def test_broker_redacts_secret_from_http_error_before_returning_to_callers(
    broker_get: Callable[[str], JsonObject],
) -> None:
    with pytest.raises(BrokerRequestError) as raised:
        broker_get("/error")

    assert "synthetic-secret" not in str(raised.value)
    assert "DUMMY_AUTH_FAILURE" in str(raised.value)


@pytest.mark.parametrize("cache", (b"[]", b"null", b"true", b'"text"', b"\xff"))
def test_kis_ignores_malformed_token_cache_without_crashing(
    tmp_path: Path, cache: bytes
) -> None:
    # Given an invalid token cache isolated from operator state.
    path = tmp_path / "cache.json"
    path.write_bytes(cache)
    client = KISClient(
        KISCredentials("dummy-key", "dummy-secret", "12345678"),
        token_cache_path=path,
    )

    # When attempting to restore the token.
    restored = client._load_cached_token(datetime.now(timezone.utc))

    # Then normal token acquisition may proceed without an invalid cached token.
    assert restored is False
    assert client._access_token is None
