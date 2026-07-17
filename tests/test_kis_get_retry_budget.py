from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.client import RemoteDisconnected
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

import pytest

from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.brokers.common import JsonObject
from nasdaq_auto_trader.brokers.kis_client import KISClient, KISCredentials


class FakeClock:
    __slots__ = ("now", "sleeps")

    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_get_retries_twice_with_injected_bounded_backoff(tmp_path: Path) -> None:
    clock = FakeClock()
    client = _client(tmp_path, clock)
    with patch.object(
        client,
        "_open_json",
        side_effect=[RemoteDisconnected(), RemoteDisconnected(), {"rt_cd": "0"}],
    ) as opened:
        result = client._request(
            "GET",
            "/safe-read",
            "READ",
            deadline=clock.now + 10.0,
        )

    assert result == {"rt_cd": "0"}
    assert opened.call_count == 3
    assert clock.sleeps == [0.5, 1.0]


def test_get_does_not_begin_retry_past_tick_deadline(tmp_path: Path) -> None:
    clock = FakeClock()
    client = _client(tmp_path, clock)
    with patch.object(
        client,
        "_open_json",
        side_effect=RemoteDisconnected(),
    ) as opened:
        with pytest.raises(BrokerRequestError, match="deadline exceeded"):
            client._request(
                "GET",
                "/safe-read",
                "READ",
                deadline=clock.now + 0.4,
            )

    assert opened.call_count == 1
    assert clock.sleeps == []


def test_reconciliation_window_shares_one_deadline_across_endpoints(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    client = _client(tmp_path, clock)
    observed_timeouts: list[float] = []
    responses = iter(({"output": []}, {"output": []}))

    def open_json(_request: Request, _label: str) -> JsonObject:
        observed_timeouts.append(client._active_timeout_seconds or 0.0)
        clock.now += 6.0
        return next(responses)

    with patch.object(client, "_open_json", side_effect=open_json):
        with client.reconciliation_window(10.0):
            assert client.list_open_orders() == ()
            assert client.list_order_history("20260717", "20260717") == ()

    assert observed_timeouts == [8.0, 4.0]


def _client(tmp_path: Path, clock: FakeClock) -> KISClient:
    credentials = KISCredentials("app", "secret", "12345678", paper=False)
    client = KISClient(
        credentials,
        tmp_path / "token.json",
        retry_clock=clock.clock,
        retry_sleep=clock.sleep,
        retry_jitter=lambda: 0.0,
    )
    client._access_token = "test-token"
    client._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return client
