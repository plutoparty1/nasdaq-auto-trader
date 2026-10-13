from dataclasses import replace
from pathlib import Path

import pytest

from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_audit import AutomaticOrderAuditor
from nasdaq_auto_trader.automatic_order_types import AutomaticOrderContext, AutomaticOrderPermit
from nasdaq_auto_trader.broker_response import broker_response_submitted
from nasdaq_auto_trader.session_claims import ClaimStatus, SignalKey
from nasdaq_auto_trader.trading_session_store import SafetyReservationRequest, TradingSessionStore


@pytest.mark.parametrize("response", [{}, {"status": "unknown"}, {"status": "unrecognized"}])
def test_ambiguous_response_blocks_later_signal_until_reconciled(tmp_path: Path, response):
    # Given an order with a durable submission reservation.
    store = TradingSessionStore(tmp_path / "session.json")
    key = SignalKey("2026-09-09", "test", "v1", "AAPL", "buy", "first")
    request = SafetyReservationRequest(
        "2026-09-09", "buy", "2026-09-09T14:00:00+00:00", 0, 0, 0, False, False, True, 0
    )
    assert store.claim_and_reserve_safety(key, request).granted
    context = AutomaticOrderContext(
        "test", "v1", "test", "test", "2026-09-09", "test", "live", "first",
        0, 0, 0, False, False, True,
    )

    # When the broker cannot establish the order outcome.
    result = AutomaticOrderAuditor(NullAuditLogger(), store).finish(
        AutomaticOrderPermit(key, context, 0), response
    )

    # Then the uncertainty survives and prevents a different signal.
    assert result is not None and result.terminal
    decision = store.claim_and_reserve_safety(replace(key, signal_timestamp="second"), request)
    assert not decision.granted
    assert decision.reason == "automatic_order_reconciliation_required"


@pytest.mark.parametrize("status", [ClaimStatus.UNCERTAIN, ClaimStatus.SUBMITTING])
def test_unresolved_previous_day_order_blocks_next_market_day(tmp_path: Path, status: ClaimStatus):
    # Given an unresolved order from the previous market day.
    store = TradingSessionStore(tmp_path / "session.json")
    key = SignalKey("2026-09-09", "test", "v1", "AAPL", "buy", "first")
    store.claim(key)
    if status is ClaimStatus.UNCERTAIN:
        store.complete(key, status)

    # When a different signal arrives the following day.
    result = store.claim_and_reserve_safety(
        replace(key, market_date="2026-09-10", signal_timestamp="next-day"),
        SafetyReservationRequest(
            "2026-09-10", "buy", "2026-09-10T14:00:00+00:00", 0, 0, 0, False, False, True, 0
        ),
    )

    # Then changing the market date cannot clear an unresolved order.
    assert not result.granted


def test_partially_filled_order_counts_as_submitted():
    # Given an accepted order with an initial partial fill.
    response = {"status": "partially_filled", "id": "test-order"}
    # When submission accounting classifies the response.
    submitted = broker_response_submitted(response)
    # Then the filled exposure remains accounted for.
    assert submitted
