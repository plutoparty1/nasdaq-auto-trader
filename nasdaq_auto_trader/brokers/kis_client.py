from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
import random
import time

from nasdaq_auto_trader.quant_data.resources import application_data_root
from nasdaq_auto_trader.live_canary_identity import account_fingerprint
from nasdaq_auto_trader.live_canary_lease import BrokerLiveLease

from .common import BrokerCredentialError, JsonObject
from .kis_account import KISAccountMixin
from .kis_auth import KISAuthMixin
from .kis_market import KISMarketDataMixin
from .kis_order import KISOrderMixin
from .kis_reconciliation import KISReconciliationMixin


@dataclass(frozen=True, slots=True)
class KISCredentials:
    """Korea Investment & Securities Open API credentials."""

    app_key: str
    app_secret: str
    account_no: str
    account_product_code: str = "01"
    paper: bool = True
    order_exchange_code: str = "NASD"
    price_exchange_code: str = "NAS"
    currency: str = "USD"
    timeout: int = 30


class KISClient(KISAccountMixin, KISOrderMixin, KISMarketDataMixin, KISReconciliationMixin, KISAuthMixin):
    real_base_url = "https://openapi.koreainvestment.com:9443"
    paper_base_url = "https://openapivts.koreainvestment.com:29443"

    def __init__(
        self,
        credentials: KISCredentials,
        token_cache_path: str | Path | None = None,
        *,
        retry_clock: Callable[[], float] = time.monotonic,
        retry_sleep: Callable[[float], None] | None = None,
        retry_jitter: Callable[[], float] = lambda: random.uniform(0.0, 0.25),
    ) -> None:
        missing = [
            name
            for name, value in (
                ("KIS_APP_KEY", credentials.app_key),
                ("KIS_APP_SECRET", credentials.app_secret),
                ("KIS_ACCOUNT_NO", credentials.account_no),
            )
            if not value
        ]
        if missing:
            raise BrokerCredentialError(
                f"KIS credentials are required: {', '.join(missing)}"
            )
        self.credentials = credentials
        self.base_url = self.paper_base_url if credentials.paper else self.real_base_url
        self._token_cache_path = (
            Path(token_cache_path)
            if token_cache_path is not None
            else application_data_root() / "runtime" / ".kis_token.json"
        )
        self._access_token: str | None = None
        self._token_expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self._balance_payload: JsonObject | None = None
        self._present_balance_payload: JsonObject | None = None
        self._token_cache_write_error: OSError | None = None
        self._last_tr_cont = ""
        self._active_timeout_seconds: float | None = None
        self._retry_clock = retry_clock
        self._retry_sleep = retry_sleep
        self._retry_jitter = retry_jitter
        self.account_fingerprint = account_fingerprint(
            credentials.account_no,
            credentials.account_product_code,
        )
        self._broker_lease_path = (
            application_data_root() / "live_canary" / "broker-live-owner.lock"
        )
        self._broker_live_lease: BrokerLiveLease | None = None

    def bind_live_lease(self, lease: BrokerLiveLease) -> None:
        lease.assert_allowed(
            self._broker_lease_path,
            self.account_fingerprint,
            next(iter(lease.allowed_sides)),
        )
        self._broker_live_lease = lease
