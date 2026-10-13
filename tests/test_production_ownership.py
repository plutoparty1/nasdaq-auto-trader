from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request

import pytest

from nasdaq_auto_trader.broker import KISCredentials
from nasdaq_auto_trader.brokers.common import BrokerRequestError
from nasdaq_auto_trader.brokers.kis_client import KISClient
from nasdaq_auto_trader.brokers.kis_reconciliation import KISOpenOrder, KISOrderHistory
from nasdaq_auto_trader.models import Position
from nasdaq_auto_trader.production_checks import ProductionReadOnlyClient
from nasdaq_auto_trader.production_ownership import (
    ProductionSessionStore,
    foreign_portfolio_counts,
)
from nasdaq_auto_trader.session_claims import AcceptedBuyReceipt, ClaimStatus, SignalKey
from nasdaq_auto_trader.trading_session_store import SessionStoreError


def test_resolved_receipt_remains_proof_of_own_order_after_restart(tmp_path: Path) -> None:
    # Given: an accepted sandbox order from an initially flat production session.
    store = ProductionSessionStore(tmp_path / "session.json", "sandbox-account")
    key = SignalKey("2026-10-13", "s", "v", "TEST", "buy", "bar")
    assert store.claim(key).granted
    receipt = AcceptedBuyReceipt("fake-order", "TEST", "2026-10-13", 0)
    store.complete(key, ClaimStatus.SUBMITTED, receipt)
    store.resolve_buy_receipt(key.digest())
    # When: the production session is reopened.
    restored = ProductionSessionStore(store.path, "sandbox-account").managed_receipts()
    # Then: ordinary receipt reconciliation does not erase ownership provenance.
    assert restored == (receipt,)
    assert store.load_buy_receipts() == ()


def test_other_account_cannot_inherit_owned_order_receipt(tmp_path: Path) -> None:
    # Given: a persisted receipt belonging to one sandbox account.
    store = ProductionSessionStore(tmp_path / "session.json", "sandbox-one")
    key = SignalKey("2026-10-13", "s", "v", "TEST", "buy", "bar")
    assert store.claim(key).granted
    store.complete(key, ClaimStatus.SUBMITTED, AcceptedBuyReceipt("fake-order", "TEST", "2026-10-13", 0))
    # When: a different account reads that record.
    # Then: it fails closed instead of inheriting ownership.
    with pytest.raises(SessionStoreError, match="production_managed_receipts_binding_mismatch"):
        ProductionSessionStore(store.path, "sandbox-two").managed_receipts()


def test_only_matching_owned_position_and_partial_order_pass_readonly_reconciliation() -> None:
    # Given: an own half-filled 1-share buy and an unrelated foreign holding.
    receipt = AcceptedBuyReceipt("fake-order", "TEST", "2026-10-13", 0)
    history = KISOrderHistory("fake-order", "TEST", "buy", 1, 0.5, 20.61, "partially_filled",
                              datetime(2026, 10, 13, 15, tzinfo=UTC))
    own = Position("TEST", 0.5, 10.305, 20.61)
    order = KISOpenOrder("fake-order", "TEST", "buy", 1, 0.5, 0.5, 20.61)
    # When: preflight compares the local receipt with broker state.
    counts = foreign_portfolio_counts({"TEST": own, "FOREIGN": replace(own, symbol="FOREIGN")},
                                      (order, replace(order, order_id="external-order")),
                                      ((receipt,), (history,)))
    # Then: only the recorded own objects are eligible; external holdings/orders remain blocked.
    assert counts == (1, 1)


def test_readonly_history_allowed_but_order_post_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the production read-only KIS transport and a fake base transport.
    monkeypatch.setattr(KISClient, "_open_json", lambda *_args: {})
    client = ProductionReadOnlyClient(KISCredentials("fake", "fake", "00000000", paper=False))
    base = "https://example.invalid/uapi/overseas-stock/v1/trading/"
    # When: order history is read and a write endpoint is attempted.
    history = client._open_json(Request(base + "inquire-ccnl"), "history")
    # Then: history can reach the fake read transport, while order submission is forbidden.
    assert history == {}
    with pytest.raises(BrokerRequestError, match="preflight_transport_not_allowed"):
        client._open_json(Request(base + "order", data=b"{}", method="POST"), "order")


@pytest.mark.parametrize("timestamp", [None, datetime(2026, 10, 13, 15, tzinfo=UTC)])
def test_order_id_reuse_on_different_day_does_not_prove_ownership(timestamp: datetime | None) -> None:
    # Given: an old owned order ID reused by a newer foreign buy.
    receipt = AcceptedBuyReceipt("same-id", "TEST", "2026-10-12", 0)
    history = KISOrderHistory("same-id", "TEST", "buy", 1, 1, 20.61,
                              "filled", timestamp)
    # When: today's holding is compared with the old receipt.
    counts = foreign_portfolio_counts({"TEST": Position("TEST", 1, 20.61, 20.61)}, (),
                                      ((receipt,), (history,)))
    # Then: the different market date prevents accidental adoption.
    assert counts == (1, 0)
