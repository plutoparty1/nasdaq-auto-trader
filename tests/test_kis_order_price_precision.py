from decimal import Decimal
from pathlib import Path

import pytest

from nasdaq_auto_trader.brokers.kis_client import KISCredentials
from nasdaq_auto_trader.brokers.kis_order import KISOrderMixin
from nasdaq_auto_trader.brokers.kis_pricing import normalize_kis_limit_price
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest, OrderSide, Position


class CapturingKISOrderClient(KISOrderMixin):
    def __init__(self, lease_path: Path) -> None:
        self.credentials = KISCredentials("app", "secret", "12345678")
        self._broker_lease_path = lease_path
        self._broker_live_lease = None
        self.account_fingerprint = "test-account"
        self.posted_body: dict[str, str] | None = None
        self.buying_power_price: float | None = None

    def get_account(self, refresh: bool = False) -> AccountSnapshot:
        return AccountSnapshot(cash=1_000, equity=1_000, buying_power=1_000)

    def get_overseas_buying_power(
        self,
        symbol: str,
        order_price: float | None = None,
    ) -> float:
        self.buying_power_price = order_price
        return 1_000.0

    def get_latest_price(self, symbol: str) -> float:
        return 27.075

    def list_positions(self, refresh: bool = False) -> dict[str, Position]:
        return {"WBD": Position("WBD", 1, 25.8, 27.075)}

    def _request(
        self,
        method: str,
        path: str,
        tr_id: str,
        params: dict[str, str] | None = None,
        body: dict[str, str] | None = None,
    ) -> dict[str, str]:
        self.posted_body = body
        return {"rt_cd": "0"}


def test_kis_sell_rounds_price_down_to_two_decimals_at_or_above_one_dollar(
    tmp_path: Path,
) -> None:
    # Given
    client = CapturingKISOrderClient(tmp_path / "broker.lock")
    order = OrderRequest("WBD", "sell", qty=1, limit_price=27.075)

    # When
    client.submit_order(order)

    # Then
    assert client.posted_body is not None
    assert client.posted_body["OVRS_ORD_UNPR"] == "27.07"


def test_kis_buy_rounds_price_up_before_buying_power_and_post(
    tmp_path: Path,
) -> None:
    # Given
    client = CapturingKISOrderClient(tmp_path / "broker.lock")
    order = OrderRequest("WBD", "buy", qty=1, limit_price=27.075)

    # When
    client.submit_order(order)

    # Then
    assert client.buying_power_price == 27.08
    assert client.posted_body is not None
    assert client.posted_body["OVRS_ORD_UNPR"] == "27.08"


@pytest.mark.parametrize(
    ("raw_price", "side", "expected"),
    [
        ("27.075", "sell", "27.07"),
        ("27.075", "buy", "27.08"),
        ("0.12345", "sell", "0.1234"),
        ("0.12345", "buy", "0.1235"),
        ("0.99999", "buy", "1.00"),
    ],
)
def test_kis_price_normalizer_uses_exchange_tick_and_marketable_direction(
    raw_price: str,
    side: OrderSide,
    expected: str,
) -> None:
    # Given
    price = Decimal(raw_price)

    # When
    normalized = normalize_kis_limit_price(price, side)

    # Then
    assert str(normalized) == expected
