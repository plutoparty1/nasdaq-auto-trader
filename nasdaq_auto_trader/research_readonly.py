from __future__ import annotations

import json
import ssl
import time
from collections.abc import Callable
from http.client import HTTPException, HTTPSConnection
from urllib.parse import urlencode

from .research_readonly_contract import (
    AUTH,
    DAILY,
    HISTORY,
    HOST,
    MINUTE,
    PORT,
    SYMBOLS,
    Credentials,
    JsonMap,
    JsonValue,
    Query,
    ResearchError,
    Wire,
    WireRequest,
    WireResponse,
    validate_query,
    validate_wire,
)

__all__ = [
    "AUTH",
    "DAILY",
    "HISTORY",
    "MINUTE",
    "SYMBOLS",
    "Credentials",
    "JsonMap",
    "JsonValue",
    "Query",
    "ReadOnlyKIS",
    "ResearchError",
    "Wire",
    "WireRequest",
    "WireResponse",
    "https_wire",
    "validate_query",
    "validate_wire",
]


def https_wire(request: WireRequest) -> WireResponse:
    """Fixed TLS host, no proxy, no redirect handler, no automatic retry."""
    validate_wire(request)
    connection = HTTPSConnection(
        HOST, PORT, timeout=15, context=ssl.create_default_context()
    )
    try:
        connection.request(
            request.method, request.path, request.body, dict(request.headers)
        )
        response = connection.getresponse()
        content = response.read(8_000_001)
        if len(content) > 8_000_000:
            raise ResearchError("response_size_limit")
        return WireResponse(response.status, content, response.getheader("tr_cont", ""))
    finally:
        connection.close()


class ReadOnlyKIS:
    """Memory-only token and bounded request counters for a research run."""

    def __init__(
        self,
        credentials: Credentials,
        wire: Wire = https_wire,
        *,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if any(
            not value or any(ord(char) < 33 or ord(char) > 126 for char in value)
            for value in (
                credentials.app_key,
                credentials.app_secret,
                credentials.account,
                credentials.product,
            )
        ):
            raise ResearchError("credential_header_invalid")
        self.credentials = credentials
        self.wire = wire
        self.sleeper = sleeper
        self.token = ""
        self.counts = {
            "auth": 0,
            "daily": 0,
            "history": 0,
            "minute": 0,
            "order": 0,
            "cancel": 0,
        }

    def authenticate(self) -> None:
        if self.counts["auth"]:
            raise ResearchError("authentication_attempt_limit")
        c = self.credentials
        body = json.dumps(
            {
                "grant_type": "client_credentials",
                "appkey": c.app_key,
                "appsecret": c.app_secret,
            }
        ).encode()
        request = WireRequest("POST", AUTH, {"Content-Type": "application/json"}, body)
        payload, _ = self._exchange(request, "auth")
        token = payload.get("access_token")
        if (
            not isinstance(token, str)
            or not token
            or any(ord(char) < 33 or ord(char) > 126 for char in token)
        ):
            raise ResearchError("authentication_token_missing")
        self.token = token

    def get(self, query: Query) -> tuple[JsonMap, str]:
        validate_query(query, self.credentials)
        if not self.token:
            raise ResearchError("authentication_required")
        headers = {
            "authorization": f"Bearer {self.token}",
            "appkey": self.credentials.app_key,
            "appsecret": self.credentials.app_secret,
            "tr_id": query.tr_id,
            "custtype": "P",
            "tr_cont": query.continuation,
            "Accept": "application/json",
        }
        request = WireRequest(
            "GET", query.path + "?" + urlencode(query.params), headers
        )
        label = {DAILY: "daily", HISTORY: "history", MINUTE: "minute"}[query.path]
        return self._exchange(request, label)

    def _exchange(self, request: WireRequest, label: str) -> tuple[JsonMap, str]:
        for attempt in range(1 if label == "auth" else 2):
            self.sleeper(0.6 + attempt)
            self.counts[label] += 1
            try:
                validate_wire(request)
                response = self.wire(request)
            except (OSError, TimeoutError, HTTPException):
                if attempt == 0 and label != "auth":
                    continue
                raise ResearchError("transport_unavailable") from None
            if 300 <= response.status < 400:
                raise ResearchError("redirect_denied")
            if response.status == 429 and attempt == 0 and label != "auth":
                continue
            if response.status != 200:
                raise ResearchError(f"http_status_{response.status}")
            try:
                payload = json.loads(response.content)
            except (ValueError, UnicodeError):
                raise ResearchError("response_json_invalid") from None
            if not isinstance(payload, dict):
                raise ResearchError("response_shape_invalid")
            if payload.get("rt_cd") not in (None, "0"):
                if (
                    payload.get("msg_cd") == "EGW00201"
                    and attempt == 0
                    and label != "auth"
                ):
                    continue
                raise ResearchError("api_rejected")
            return payload, response.continuation
        raise ResearchError("retry_limit")
