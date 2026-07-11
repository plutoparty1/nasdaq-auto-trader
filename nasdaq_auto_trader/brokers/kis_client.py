from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.quant_data.resources import application_data_root

from .common import BrokerCredentialError, JsonObject
from .kis_account import KISAccountMixin
from .kis_auth import KISAuthMixin
from .kis_market import KISMarketDataMixin
from .kis_order import KISOrderMixin


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


class KISClient(KISAccountMixin, KISOrderMixin, KISMarketDataMixin, KISAuthMixin):
    real_base_url = "https://openapi.koreainvestment.com:9443"
    paper_base_url = "https://openapivts.koreainvestment.com:29443"

    def __init__(
        self,
        credentials: KISCredentials,
        token_cache_path: str | Path | None = None,
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
        self._token_cache_write_error: OSError | None = None
