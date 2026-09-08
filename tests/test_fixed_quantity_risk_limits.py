from dataclasses import replace

import pytest

from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest, Position, TradeDecision
from nasdaq_auto_trader.risk import RiskConfig, RiskManager


@pytest.mark.parametrize(
    ("config", "account", "position", "risk_per_share", "ceiling"),
    [
        (RiskConfig(max_position_pct=0.01), AccountSnapshot(10_000, 10_000, 10_000), None, None, 100),
        (RiskConfig(), AccountSnapshot(600, 10_000, 10_000), None, None, 100),
        (RiskConfig(), AccountSnapshot(10_000, 10_000, 100), None, None, 100),
        (RiskConfig(max_order_notional=100), AccountSnapshot(10_000, 10_000, 10_000), None, None, 100),
        (RiskConfig(), AccountSnapshot(10_000, 10_000, 10_000), Position("QQQ", 9, 900, 100), None, 100),
        (RiskConfig(), AccountSnapshot(10_000, 10_000, 10_000), None, 100, 100),
    ],
    ids=["position-weight", "cash-reserve", "buying-power", "order-value", "existing-exposure", "atr-risk"],
)
@pytest.mark.parametrize("order_qty", [None, 2], ids=["notional", "fixed"])
def test_buy_respects_each_ceiling(
    config: RiskConfig,
    account: AccountSnapshot,
    position: Position | None,
    risk_per_share: float | None,
    ceiling: float,
    order_qty: int | None,
) -> None:
    # Given an independently binding risk ceiling below two shares.
    manager = RiskManager(replace(config, order_qty=order_qty))
    decision = TradeDecision("QQQ", "buy", 10, 100, risk_per_share=risk_per_share)

    # When sizing the buy.
    order = manager.build_order(decision, account, position, 100)

    # Then fixed size is refused and variable size fits the same ceiling.
    expected = None if order_qty else OrderRequest("QQQ", "buy", notional=ceiling)
    assert order == expected


@pytest.mark.parametrize("price", [20, 100])
def test_fixed_buy_keeps_exact_quantity_at_ceiling_even_below_notional_floor(price: float) -> None:
    # Given a two-share limit exactly at the ceiling and below a notional-mode floor.
    manager = RiskManager(RiskConfig(order_qty=2, max_order_notional=price * 2, min_order_notional=500))
    account = AccountSnapshot(10_000, 10_000, 10_000)
    decision = TradeDecision("QQQ", "buy", 10, price)

    # When sizing the fixed-share buy.
    order = manager.build_order(decision, account, None, price)

    # Then the explicit share quantity is preserved without increasing it to meet the floor.
    assert order == OrderRequest("QQQ", "buy", type="limit", qty=2, limit_price=price)


@pytest.mark.parametrize("field", ["cash", "equity", "buying_power"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
@pytest.mark.parametrize("order_qty", [None, 1])
def test_buy_rejects_invalid_account_exposure(field: str, value: float, order_qty: int | None) -> None:
    # Given a malformed account snapshot.
    account = replace(AccountSnapshot(10_000, 10_000, 10_000), **{field: value})
    manager = RiskManager(RiskConfig(order_qty=order_qty))
    decision = TradeDecision("QQQ", "buy", 10, 100)

    # When sizing a buy.
    order = manager.build_order(decision, account, None, 100)

    # Then malformed exposure never creates an order.
    assert order is None


@pytest.mark.parametrize("field", ["qty", "market_value"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
@pytest.mark.parametrize("order_qty", [None, 1])
def test_buy_rejects_invalid_position_exposure(field: str, value: float, order_qty: int | None) -> None:
    # Given a position whose exposure cannot be used for safe sizing.
    position = replace(Position("QQQ", 1, 100, 100), **{field: value})
    manager = RiskManager(RiskConfig(order_qty=order_qty))
    account = AccountSnapshot(10_000, 10_000, 10_000)
    decision = TradeDecision("QQQ", "buy", 10, 100)

    # When sizing a buy against that position.
    order = manager.build_order(decision, account, position, 100)

    # Then no order can be created.
    assert order is None


@pytest.mark.parametrize("price", [float("nan"), float("inf"), -1.0, 0.0])
@pytest.mark.parametrize("order_qty", [None, 1])
def test_buy_rejects_invalid_price(price: float, order_qty: int | None) -> None:
    # Given an unusable execution price.
    manager = RiskManager(RiskConfig(order_qty=order_qty))
    account = AccountSnapshot(10_000, 10_000, 10_000)
    decision = TradeDecision("QQQ", "buy", 10, price)

    # When sizing the buy.
    order = manager.build_order(decision, account, None, price)

    # Then no order can be created.
    assert order is None


@pytest.mark.parametrize(
    "config",
    [RiskConfig(order_qty=2, allow_additional_buy=False), RiskConfig(order_qty=2, max_position_qty=2),
     RiskConfig(order_qty=2, min_cash_to_buy=10_001)],
    ids=["additional-buy", "position-quantity", "minimum-cash"],
)
def test_fixed_buy_preserves_owner_limits(config: RiskConfig) -> None:
    # Given a share-specific owner limit that forbids an otherwise affordable buy.
    manager = RiskManager(config)
    account = AccountSnapshot(10_000, 10_000, 10_000)
    position = Position("QQQ", 1, 100, 100)
    decision = TradeDecision("QQQ", "buy", 10, 100)

    # When sizing the buy.
    order = manager.build_order(decision, account, position, 100)

    # Then the owner limit still prevents it.
    assert order is None


def test_sell_still_reduces_exposure_when_buying_capital_is_unusable() -> None:
    # Given existing holdings with unavailable account values and a fixed sell size.
    manager = RiskManager(RiskConfig(order_qty=2))
    position = Position("QQQ", 3, 300, 100)
    account = AccountSnapshot(float("nan"), -1, 0)
    decision = TradeDecision("QQQ", "sell", 10, 100)

    # When reducing the position.
    order = manager.build_order(decision, account, position, 100)

    # Then buy-only checks do not prevent the exit.
    assert order == OrderRequest("QQQ", "sell", qty=2)


@pytest.mark.parametrize("risk_per_share", [float("nan"), float("inf"), -1.0])
@pytest.mark.parametrize("order_qty", [None, 1])
def test_buy_rejects_invalid_risk_distance(risk_per_share: float, order_qty: int | None) -> None:
    # Given a strategy risk distance that cannot support valid risk sizing.
    manager = RiskManager(RiskConfig(order_qty=order_qty))
    account = AccountSnapshot(10_000, 10_000, 10_000)
    decision = TradeDecision("QQQ", "buy", 10, 100, risk_per_share=risk_per_share)

    # When sizing the buy.
    order = manager.build_order(decision, account, None, 100)

    # Then malformed risk input cannot bypass the cap.
    assert order is None


def test_notional_rounding_never_exceeds_risk_ceiling() -> None:
    # Given an order ceiling between valid currency increments.
    manager = RiskManager(RiskConfig(max_order_notional=100.006))
    account = AccountSnapshot(10_000, 10_000, 10_000)
    decision = TradeDecision("QQQ", "buy", 10, 100)

    # When creating a cent-denominated order.
    order = manager.build_order(decision, account, None, 100)

    # Then rounding remains within the ceiling.
    assert order == OrderRequest("QQQ", "buy", notional=100)
