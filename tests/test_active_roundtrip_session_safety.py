import json
import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.session_claims import ClaimStatus, SignalKey
from nasdaq_auto_trader.trading_session_store import (
    PersistedSafetyState,
    SafetyReservationRequest,
    TradingSessionStore,
)


class ActiveRoundtripSessionSafetyTests(unittest.TestCase):
    def test_runtime_date_advance_preserves_unresolved_session_claims(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingSessionStore(Path(temp_dir) / "session.json")
            store.save_safety_state(
                PersistedSafetyState(market_date="2026-07-13")
            )
            store.claim(_key("2026-07-13"))
            store.recover_interrupted_claims()
            store.merge_safety_state(
                PersistedSafetyState(market_date="2026-07-14")
            )

            decision = store.claim_and_reserve_safety(
                _key("2026-07-14"),
                _reservation("2026-07-14"),
            )

        self.assertFalse(decision.granted)
        self.assertEqual(decision.reason, "automatic_order_reconciliation_required")

    def test_previous_market_date_uncertain_claim_requires_resolution_before_new_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingSessionStore(Path(temp_dir) / "session.json")
            store.save_safety_state(
                PersistedSafetyState(market_date="2026-07-13")
            )
            store.claim(_key("2026-07-13"))
            store.recover_interrupted_claims()

            first_key = _key("2026-07-14")
            decision = store.claim_and_reserve_safety(
                first_key,
                _reservation("2026-07-14"),
            )
            self.assertFalse(decision.granted)
            self.assertEqual(decision.reason, "automatic_order_reconciliation_required")
            store.complete(_key("2026-07-13"), ClaimStatus.SUBMITTED)
            reconciled = store.claim_and_reserve_safety(
                first_key,
                _reservation("2026-07-14"),
            )
            store.complete(first_key, ClaimStatus.SUBMITTED)
            second = store.claim_and_reserve_safety(
                _key("2026-07-14", "MSFT"),
                _reservation("2026-07-14"),
            )
            safety = store.load_safety_state()

        self.assertTrue(reconciled.granted)
        self.assertTrue(second.granted)
        self.assertEqual(safety.market_date, "2026-07-14")
        self.assertEqual(safety.buy_count, 2)

    def test_legacy_uncertain_claim_blocks_later_signal_on_same_market_date(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.json"
            original = _key("2026-07-13")
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "safety": {
                            "market_date": "2026-07-13",
                            "buy_count": 0,
                            "sell_count": 0,
                            "last_order_at": "",
                            "daily_loss_breached": False,
                            "baseline_observed": False,
                        },
                        "claims": {original.digest(): "uncertain"},
                    }
                ),
                encoding="utf-8",
            )
            store = TradingSessionStore(path)

            same_day = store.claim_and_reserve_safety(
                _key("2026-07-13", "MSFT"),
                _reservation("2026-07-13"),
            )
            next_day = store.claim_and_reserve_safety(
                _key("2026-07-14"),
                _reservation("2026-07-14"),
            )

        self.assertFalse(same_day.granted)
        self.assertEqual(
            same_day.reason,
            "automatic_order_reconciliation_required",
        )
        self.assertFalse(next_day.granted)
        self.assertEqual(next_day.reason, "automatic_order_reconciliation_required")


def _key(market_date: str, symbol: str = "AAPL") -> SignalKey:
    return SignalKey(
        market_date,
        "alpha",
        "v1",
        symbol,
        "buy",
        f"{market_date}T14:30:00+00:00",
    )


def _reservation(market_date: str) -> SafetyReservationRequest:
    return SafetyReservationRequest(
        market_date=market_date,
        side="buy",
        timestamp=f"{market_date}T14:30:00+00:00",
        max_daily_buy_count=0,
        max_daily_sell_count=0,
        max_daily_order_count=0,
        cooldown_minutes=0,
        daily_loss_breached=False,
        daily_loss_state_unavailable=False,
        baseline_available=True,
    )


if __name__ == "__main__":
    unittest.main()
