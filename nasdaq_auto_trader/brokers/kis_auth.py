from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from http.client import RemoteDisconnected
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .common import BrokerRequestError


class KISAuthMixin:
    def _request(
        self,
        method: str,
        path: str,
        tr_id: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        self._ensure_token()
        query = f"?{urlencode(params)}" if params else ""
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}{query}",
            data=data,
            method=method,
            headers={
                "authorization": f"Bearer {self._access_token}",
                "appkey": self.credentials.app_key,
                "appsecret": self.credentials.app_secret,
                "tr_id": tr_id,
                "custtype": "P",
                "tr_cont": "",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            return self._open_json(request, "KIS API")
        except RemoteDisconnected:
            if method != "GET":
                raise
            time.sleep(0.5)
            return self._open_json(request, "KIS API")
        except RuntimeError as exc:
            if method != "GET" or "EGW00201" not in str(exc):
                raise
            time.sleep(1.05)
            return self._open_json(request, "KIS API")

    def _ensure_token(self) -> None:
        now = datetime.now(timezone.utc)
        if self._access_token and now < self._token_expires_at:
            return
        if self._load_cached_token(now):
            return
        body = {
            "grant_type": "client_credentials",
            "appkey": self.credentials.app_key,
            "appsecret": self.credentials.app_secret,
        }
        request = Request(
            f"{self.base_url}/oauth2/tokenP",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        payload = self._open_json(request, "KIS token")
        token = payload.get("access_token")
        if not token:
            raise BrokerRequestError(
                f"KIS token response missing access_token: {payload}"
            )
        self._access_token = str(token)
        expires_in = int(payload.get("expires_in", 86400))
        self._token_expires_at = now + timedelta(seconds=max(expires_in - 60, 60))
        self._write_cached_token()

    def _load_cached_token(self, now: datetime) -> bool:
        try:
            payload = json.loads(self._token_cache_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return False

        if payload.get("cache_key") != self._token_cache_key():
            return False
        token = payload.get("access_token")
        expires_at_raw = payload.get("expires_at")
        if not token or not expires_at_raw:
            return False
        try:
            expires_at = datetime.fromisoformat(str(expires_at_raw))
        except ValueError:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now >= expires_at:
            return False

        self._access_token = str(token)
        self._token_expires_at = expires_at
        return True

    def _write_cached_token(self) -> None:
        payload = {
            "cache_key": self._token_cache_key(),
            "access_token": self._access_token,
            "expires_at": self._token_expires_at.isoformat(),
        }
        try:
            self._token_cache_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            self._token_cache_write_error = exc

    def _token_cache_key(self) -> str:
        source = f"{self.base_url}|{self.credentials.app_key}"
        return sha256(source.encode("utf-8")).hexdigest()

    def _open_json(self, request: Request, label: str) -> Any:
        try:
            with urlopen(request, timeout=self.credentials.timeout) as response:
                text = response.read().decode("utf-8")
        except HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace")
            raise BrokerRequestError(f"{label} error {exc.code}: {error_text}") from exc

        if not text:
            return {}
        payload = json.loads(text)
        if isinstance(payload, dict) and payload.get("rt_cd") not in (None, "0"):
            message = payload.get("msg1") or payload.get("msg_cd") or payload
            raise BrokerRequestError(f"{label} error: {message}")
        return payload
