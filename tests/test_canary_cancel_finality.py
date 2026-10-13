from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from nasdaq_auto_trader.brokers.kis_reconciliation import KISOpenOrder
from nasdaq_auto_trader.live_canary_policy import OrderSide
from nasdaq_auto_trader.live_canary_state import CanaryStateStore, OrderIntent, StateMode
from nasdaq_auto_trader.models import Position
from tests.live_canary_runner_fixtures import NOW, FakeKIS, armed_canary, run_canary


def test_cancel_acceptance_retains_order_and_never_posts_replacement(tmp_path: Path) -> None:
    paths, config, executable = armed_canary(tmp_path)
    store = CanaryStateStore(paths.state)
    state = store.load(expected_nonce="nonce").with_owned_position("WBD", 1)
    state = replace(state, confirmed_entry_price_usd=Decimal("19"))
    intent = OrderIntent("WBD", OrderSide.SELL, 1, Decimal("18.9"))
    state = state.record_intent(intent).complete_intent("sell-original", NOW - timedelta(minutes=1))
    store.save(state)
    broker = FakeKIS(
        {"WBD": Position("WBD", 1.0, 18.0, 19.0)},
        open_orders=(KISOpenOrder("sell-original", "WBD", "sell", 1, 0, 1, 18.9),),
        latest_price=18.0,
    )

    result = run_canary(config, paths, executable, broker)
    persisted = store.load(expected_nonce="nonce")

    assert len(broker.cancels) == 1
    assert broker.posts == 0
    assert persisted.known_order is not None
    assert persisted.known_order.order_id == "sell-original"
    assert persisted.mode is StateMode.MANUAL_RECONCILIATION_REQUIRED
    assert result.reason == "cancel_finality_requires_reconciliation"
