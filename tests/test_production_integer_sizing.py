from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest

from nasdaq_auto_trader.models import AccountSnapshot, Position, TradeDecision
from nasdaq_auto_trader.risk import RiskConfig, RiskManager


def configured_risk() -> RiskConfig:
    return RiskConfig(integer_quantity_enabled=True, order_qty=None,
                      max_position_pct=.30, min_order_notional=0,
                      max_order_notional=35, risk_per_trade_pct=.01,
                      min_cash_buffer_pct=.05, allow_additional_buy=False,
                      estimated_roundtrip_cost_pct=.005)


@pytest.mark.parametrize("price,stop,expected", [(20.61, .6183, 0), (5, .15, 3),
                                                (1, .03, 17), (40, 1.2, 0)])
def test_whole_share_size_floors_conservative_limits(price: float, stop: float,
                                                   expected: int) -> None:
    # Given: all cost and risk numbers are explicitly synthetic test inputs.
    account = AccountSnapshot(62.91, 62.91, 62.91)
    decision = TradeDecision("TEST", "buy", 8, price, ["normal_signal"], stop)
    # When: adaptive whole-share sizing receives the same account and live-price input.
    order = RiskManager(configured_risk()).build_order(decision, account, None, price)
    # Then: it floors affordability without promoting a zero quantity into one.
    assert (order.qty if order is not None else 0) == expected
    if order is not None:
        assert order.notional is None
        assert order.limit_price == price
        assert order.qty * price <= 35
        assert order.qty * (stop + price * .005) <= account.equity * .01


@pytest.mark.parametrize("action", ["hold", "buy"])
def test_no_signal_or_existing_position_cannot_create_integer_entry(action: Literal["hold", "buy"]) -> None:
    # Given: a held symbol cannot be added to under this candidate policy.
    risk = RiskManager(configured_risk())
    decision = TradeDecision("TEST", action, 0, 1, ["below_long_regime"], .03)
    position = Position("TEST", 2, 2, 1)
    # When: the candidate evaluates an entry or a HOLD with existing ownership.
    order = risk.build_order(decision, AccountSnapshot(100, 100, 100), position, 1)
    # Then: no automatic size can bypass the signal or no-adding rule.
    assert order is None


def test_adaptive_sizing_preserves_full_protective_exit() -> None:
    # Given: this approved candidate owns more than one share with a protective exit.
    risk = RiskManager(configured_risk())
    decision = TradeDecision("TEST", "sell", 99, .90, ["fixed_stop_loss"])
    # When: protection acts while the cash balance is zero.
    order = risk.build_order(decision, AccountSnapshot(0, 3, 0), Position("TEST", 3, 2.7, 1), .9)
    # Then: all three owned shares can close without a fixed-one truncation.
    assert order is not None
    assert order.qty == 3


def test_broker_buying_power_is_stricter_than_account_cash() -> None:
    # Given: the per-symbol broker buying power permits only two cost-inclusive shares.
    decision = TradeDecision("TEST", "buy", 8, 5, ["normal_signal"], .15)
    # When: current broker purchasing power is $10.01 although cash is $100.
    order = RiskManager(configured_risk()).build_order(
        decision, AccountSnapshot(100, 100, 10.01), None, 5,
    )
    # Then: the round-trip cost reserve means only one share fits.
    assert order is not None
    assert order.qty == 1


def test_minimum_fees_reserve_risk_before_whole_share_floor() -> None:
    # Given: two dollars of round-trip minimum fees exceeds this small account's budget.
    decision = TradeDecision("TEST", "buy", 8, 1, ["normal_signal"], .03)
    risk = replace(configured_risk(), estimated_roundtrip_minimum_cost_usd=2)
    # When: the otherwise cheap share is sized.
    order = RiskManager(risk).build_order(decision, AccountSnapshot(100, 100, 100), None, 1)
    # Then: unaffordable fees cannot be ignored or force one share.
    assert order is None


def test_multiple_owned_shares_require_exact_accepted_quantity(tmp_path: Path) -> None:
    from nasdaq_auto_trader.brokers.kis_reconciliation import KISOrderHistory
    from nasdaq_auto_trader.production_ownership import ProductionSessionStore, owned_position
    from nasdaq_auto_trader.session_claims import AcceptedBuyReceipt, ClaimStatus, SignalKey

    # Given: a recorded initially-flat buy explicitly requested five shares.
    store = ProductionSessionStore(tmp_path / "session.json", "sandbox-account")
    key = SignalKey("2026-10-13", "s", "v", "TEST", "buy", "bar")
    assert store.claim(key).granted
    receipt = AcceptedBuyReceipt("owned-five", "TEST", "2026-10-13", 0, planned_quantity=5)
    store.complete(key, ClaimStatus.SUBMITTED, receipt)
    history = KISOrderHistory("owned-five", "TEST", "buy", 5, 5, 6, "filled",
                              datetime(2026, 10, 13, 15, tzinfo=UTC))
    # When: ownership is restored and matched to broker-reported fills.
    restored = ProductionSessionStore(store.path, "sandbox-account").managed_receipts()
    # Then: five recorded shares are own; six requested shares cannot inherit that proof.
    assert restored == (receipt,)
    assert owned_position(Position("TEST", 5, 30, 6), restored, (history,))
    assert not owned_position(Position("TEST", 5, 30, 6), restored,
                              (replace(history, quantity=6),))


def test_minimum_commission_does_not_hide_additive_sell_tax() -> None:
    # Given: a $2.07 risk budget cannot cover $2 minimum commission plus $0.10 tax.
    risk = replace(configured_risk(), estimated_roundtrip_cost_pct=0,
                   estimated_roundtrip_minimum_cost_usd=2, estimated_sell_tax_pct=.01)
    decision = TradeDecision("TEST", "buy", 8, 10, ["normal_signal"], .01)
    # When: the candidate sizes the order with verified-style synthetic rates.
    order = RiskManager(risk).build_order(decision, AccountSnapshot(207, 207, 207), None, 10)
    # Then: minimum fees cannot mask tax and manufacture an affordable share.
    assert order is None


def test_learned_total_exposure_floors_only_opted_integer_quantity() -> None:
    from nasdaq_auto_trader.automatic_risk import AutomaticRiskLimits, CycleReservationLedger
    from nasdaq_auto_trader.models import OrderRequest
    # Given: five planned $6 shares, but an existing holding leaves $18 total capacity.
    order = OrderRequest("TEST", "buy", type="limit", qty=5, limit_price=6)
    decision = TradeDecision("TEST", "buy", 8, 6, ["normal_signal"], .18)
    positions = {"OTHER": Position("OTHER", 2, 12, 6)}
    # When: the candidate reserves under its reviewed total 30% policy.
    capped, reason = CycleReservationLedger().apply_limits(
        order, decision, 6, AccountSnapshot(88, 100, 88), positions,
        AutomaticRiskLimits(.3, .3, 35, 10, .01), 0, 100,
        integer_quantity_enabled=True, estimated_roundtrip_cost_pct=.005,
    )
    # Then: total exposure floors the final order to three and reserves no excess.
    assert reason == ""
    assert capped.qty == 3


def test_final_quantity_diagnostics_include_minimum_commission_and_tax() -> None:
    from nasdaq_auto_trader.order_decision_diagnostics import decision_risk_costs
    # Given: a final capped five-share order has $2 minimum commission and $0.30 tax.
    risk = replace(configured_risk(), estimated_roundtrip_cost_pct=0,
                   estimated_roundtrip_minimum_cost_usd=2, estimated_sell_tax_pct=.01)
    decision = TradeDecision("TEST", "buy", 8, 6, ["normal_signal"], .18)
    # When: diagnostics receives the final executable quantity.
    data = decision_risk_costs(decision, AccountSnapshot(1000, 1000, 1000), None,
                               risk, planned_quantity=5)
    # Then: recorded cost is $2.30 and total planned loss is $3.20 for all five shares.
    assert data["planned_quantity"] == 5
    assert data["estimated_roundtrip_cost"] == pytest.approx(2.3)
    assert data["planned_loss_including_estimated_cost"] == pytest.approx(3.2)


def test_candidate_is_pure_and_verified_fee_provenance_is_explicit() -> None:
    from nasdaq_auto_trader.config import AppConfig
    from nasdaq_auto_trader.config_settings import TradingSettings
    from nasdaq_auto_trader.production_fees import FeeSchedule
    from nasdaq_auto_trader.production_sizing import candidate_configuration
    # Given: the currently loaded fixed-one policy remains the operating configuration.
    original = AppConfig(risk=RiskConfig(order_qty=1, max_position_pct=.05,
                                        max_order_notional=35))
    settings = TradingSettings()
    fees = FeeSchedule(.001, 1, .0001, "synthetic_verified_schedule", "2026-10-13T15:00:00+00:00",
                       "sandbox-account")
    # When: the pure candidate snapshot is constructed without writing any settings.
    candidate, selected = candidate_configuration(original, settings, fees)
    # Then: current values stay intact and candidate costs retain commission minimum plus tax.
    assert original.risk.order_qty == 1
    assert original.risk.max_position_pct == .05
    assert not settings.integer_quantity_enabled
    assert candidate.risk.integer_quantity_enabled
    assert candidate.risk.order_qty is None
    assert candidate.risk.max_position_qty is None
    assert selected.integer_quantity_enabled
    assert candidate.risk.estimated_roundtrip_cost_pct == .002
    assert candidate.risk.estimated_roundtrip_minimum_cost_usd == 2
    assert candidate.risk.estimated_sell_tax_pct == .0001
    assert candidate.risk.estimated_cost_source == "synthetic_verified_schedule"
    assert candidate.risk.risk_per_trade_pct == .01
    assert candidate.risk.max_total_exposure_pct == .30
    assert candidate.risk.max_order_notional == 35
    assert not candidate.risk.allow_additional_buy
