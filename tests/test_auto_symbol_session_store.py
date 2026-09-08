import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.session_claims import ClaimStatus, SignalKey
from nasdaq_auto_trader.config_manager import (
    TradingSessionState,
    TradingSettings,
    validate_order_against_settings,
)
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest
from nasdaq_auto_trader.session_state_persistence import (
    load_session_state,
    save_session_state,
)
from nasdaq_auto_trader.trading_session_store import (
    PersistedSafetyState,
    SafetyReservationRequest,
    SessionStoreError,
    TradingSessionStore,
)


class AutoSymbolSessionStoreTests(unittest.TestCase):
    def test_zero_daily_order_limits_allow_repeated_reservations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingSessionStore(Path(temp_dir) / "session.json")
            request = SafetyReservationRequest(
                market_date="2026-07-13",
                side="buy",
                timestamp="2026-07-13T14:30:00+00:00",
                max_daily_buy_count=0,
                max_daily_sell_count=0,
                max_daily_order_count=0,
                cooldown_minutes=0,
                daily_loss_breached=False,
                daily_loss_state_unavailable=False,
                baseline_available=True,
            )

            decisions = [store.reserve_safety(request) for _ in range(20)]

        self.assertTrue(all(decision.granted for decision in decisions))

    def test_safety_reservation_is_atomic_across_store_instances(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            first = TradingSessionStore(path)
            second = TradingSessionStore(path)
            request = SafetyReservationRequest(
                market_date="2026-07-13",
                side="buy",
                timestamp="2026-07-13T14:30:00+00:00",
                max_daily_buy_count=1,
                max_daily_sell_count=1,
                cooldown_minutes=0,
                daily_loss_breached=False,
                daily_loss_state_unavailable=False,
                baseline_available=True,
            )

            granted = first.reserve_safety(request)
            denied = second.reserve_safety(request)

        self.assertTrue(granted.granted)
        self.assertFalse(denied.granted)
        self.assertEqual(denied.reason, "max_daily_buy_count_reached")

    def test_stale_runtime_save_does_not_reduce_reserved_counts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingSessionStore(Path(temp_dir) / "session.json")
            request = SafetyReservationRequest(
                market_date="2026-07-13",
                side="buy",
                timestamp="2026-07-13T14:30:00+00:00",
                max_daily_buy_count=5,
                max_daily_sell_count=5,
                cooldown_minutes=0,
                daily_loss_breached=False,
                daily_loss_state_unavailable=False,
                baseline_available=True,
            )
            store.reserve_safety(request)
            store.reserve_safety(request)

            save_session_state(
                store,
                TradingSessionState(
                    market_date="2026-07-13",
                    buy_count=1,
                    starting_equity=10_000,
                ),
            )
            persisted = store.load_safety_state()

        self.assertEqual(persisted.buy_count, 2)
    def test_same_day_restart_restores_daily_loss_breach_latch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingSessionStore(Path(temp_dir) / "session.json")
            store.save_safety_state(
                PersistedSafetyState(
                    market_date="2026-07-13",
                    daily_loss_breached=True,
                    baseline_observed=True,
                )
            )
            state = load_session_state(store)
            now = datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)

            response = validate_order_against_settings(
                OrderRequest("AAPL", "buy", qty=1),
                AccountSnapshot(9_000, 9_000, 9_000),
                None,
                TradingSettings(
                    max_daily_buy_count=5,
                    require_confirm_before_buy=False,
                ),
                state,
                now,
                "live",
            )

        self.assertEqual(response["reason"], "max_daily_loss_reached")

    def test_same_day_restart_with_lost_baseline_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingSessionStore(Path(temp_dir) / "session.json")
            store.save_safety_state(
                PersistedSafetyState(
                    market_date="2026-07-13",
                    baseline_observed=True,
                )
            )
            state = load_session_state(store)
            now = datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)

            response = validate_order_against_settings(
                OrderRequest("AAPL", "buy", qty=1),
                AccountSnapshot(9_000, 9_000, 9_000),
                None,
                TradingSettings(
                    max_daily_buy_count=5,
                    require_confirm_before_buy=False,
                ),
                state,
                now,
                "live",
            )

        self.assertEqual(response["reason"], "daily_loss_state_unavailable")
    def test_submitted_and_rejected_keys_block_after_store_reopen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            key = _key("2026-07-11T14:30:00+00:00")
            first = TradingSessionStore(path)

            claim = first.claim(key)
            first.complete(key, ClaimStatus.REJECTED)
            reopened = TradingSessionStore(path)
            second = reopened.claim(key)

        self.assertTrue(claim.granted)
        self.assertFalse(second.granted)
        self.assertEqual(second.reason, "signal_key_rejected")

    def test_new_signal_timestamp_creates_distinct_claim_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingSessionStore(Path(temp_dir) / "session.json")
            first = _key("2026-07-11T14:30:00+00:00")
            second = _key("2026-07-11T14:35:00+00:00")

            first_claim = store.claim(first)
            store.complete(first, ClaimStatus.SUBMITTED)
            second_claim = store.claim(second)

        self.assertTrue(first_claim.granted)
        self.assertTrue(second_claim.granted)
        self.assertNotEqual(first.digest(), second.digest())

    def test_recovered_submitting_claim_becomes_uncertain(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            key = _key("2026-07-11T14:30:00+00:00")
            store = TradingSessionStore(path)
            store.claim(key)

            reopened = TradingSessionStore(path)
            recovered = reopened.recover_interrupted_claims()
            repeated = reopened.claim(key)

        self.assertEqual(recovered, 1)
        self.assertFalse(repeated.granted)
        self.assertEqual(repeated.reason, "signal_key_uncertain")

    def test_uncertain_claim_blocks_a_later_signal_without_reserving_safety(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            store = TradingSessionStore(path)
            store.claim(_key("2026-07-11T14:30:00+00:00"))
            store.recover_interrupted_claims()
            request = SafetyReservationRequest(
                market_date="2026-07-11",
                side="buy",
                timestamp="2026-07-11T14:35:00+00:00",
                max_daily_buy_count=0,
                max_daily_sell_count=0,
                max_daily_order_count=0,
                cooldown_minutes=0,
                daily_loss_breached=False,
                daily_loss_state_unavailable=False,
                baseline_available=True,
            )

            decision = store.claim_and_reserve_safety(
                _key("2026-07-11T14:35:00+00:00"),
                request,
            )
            safety = store.load_safety_state()

        self.assertFalse(decision.granted)
        self.assertEqual(decision.reason, "automatic_order_reconciliation_required")
        self.assertEqual(safety.buy_count, 0)

    def test_safety_state_round_trip_contains_no_account_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            store = TradingSessionStore(path)
            state = PersistedSafetyState(
                market_date="2026-07-11",
                buy_count=2,
                sell_count=1,
                last_order_at="2026-07-11T14:30:00+00:00",
                daily_loss_breached=True,
                baseline_observed=True,
            )

            store.save_safety_state(state)
            loaded = store.load_safety_state()
            payload = path.read_text(encoding="utf-8")

        self.assertEqual(loaded, state)
        self.assertNotIn("starting_equity", payload)
        self.assertNotIn("account", payload)
        self.assertNotIn("buying_power", payload)

    def test_malformed_ledger_fails_closed_instead_of_resetting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            path.write_text("{broken", encoding="utf-8")
            store = TradingSessionStore(path)

            with self.assertRaises(SessionStoreError) as raised:
                store.claim(_key("2026-07-11T14:30:00+00:00"))

        self.assertEqual(raised.exception.reason, "session_store_corrupt")


def _key(signal_timestamp: str) -> SignalKey:
    return SignalKey(
        market_date="2026-07-11",
        strategy_id="alpha",
        strategy_version="v1",
        symbol="AAPL",
        side="buy",
        signal_timestamp=signal_timestamp,
    )


if __name__ == "__main__":
    unittest.main()
