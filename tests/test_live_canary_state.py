from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from nasdaq_auto_trader.live_canary_arm import (
    ArmEnvelopeError,
    ArmValidationContext,
    parse_arm_envelope,
    validate_arm_envelope,
)
from nasdaq_auto_trader.live_canary_identity import (
    account_fingerprint,
    executable_sha256,
)
from nasdaq_auto_trader.live_canary_policy import CANARY_POLICY, OrderSide
from nasdaq_auto_trader.live_canary_state import (
    CanaryState,
    CanaryStateCorruptError,
    CanaryStateStore,
    CanaryStateTransitionError,
    OrderIntent,
    StateMode,
)


def _envelope_payload(
    *, expires_at: datetime, issued_at: datetime = datetime(2026, 7, 17, tzinfo=UTC), executable_hash: str = "a" * 64
) -> dict[str, str]:
    return {
        "schema_version": "1", "market_date": "2026-07-17",
        "account_fingerprint": "a" * 64,
        "product": "overseas_stock",
        "base_url": "https://openapi.koreainvestment.com:9443",
        "executable_sha256": executable_hash,
        "policy_digest": CANARY_POLICY.digest, "windows_sid_sha256": "b" * 64,
        "state_nonce": "nonce-123",
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


def _state(*, mode: StateMode = StateMode.ARMED) -> CanaryState:
    return CanaryState(
        market_date="2026-07-17",
        nonce="nonce-123",
        account_fingerprint="account:abc",
        executable_sha256="a" * 64,
        mode=mode,
        owned_symbol="QQQ" if mode is StateMode.EXIT_ONLY else None,
        max_owned_quantity=1 if mode is StateMode.EXIT_ONLY else 0,
        round_trips=0,
        entry_attempts=0,
        exit_attempts=0,
        intent=None,
    )


class LiveCanaryStateTests(unittest.TestCase):
    def test_runner_transitions_confirm_and_clear_exact_owned_orders(self) -> None:
        known_buy = _state().record_intent(OrderIntent("QQQ", OrderSide.BUY, 1)).complete_intent("buy-1")

        owned = known_buy.confirm_owned_position("QQQ", 1, Decimal("19.25"))
        pending_exit = owned.record_intent(OrderIntent("QQQ", OrderSide.SELL, 1)).complete_intent("sell-1")
        exited = pending_exit.confirm_exit("sell-1")

        self.assertIsNone(exited.owned_symbol)
        self.assertEqual(exited.round_trips, 1)
        self.assertEqual(exited.exit_attempts, 0)

    def test_policy_exposes_final_scan_and_get_budgets(self) -> None:
        policy = CANARY_POLICY

        self.assertEqual((policy.rank_top_symbols, policy.deep_inspect_symbols, policy.max_detail_get_calls), (30, 10, 20))
        owned_minutes = (
            (16 * 60 - policy.forced_exit_close_minutes)
            - (9 * 60 + 30 + policy.entry_window_open_minutes)
        )
        position_polls = owned_minutes * 60 // policy.position_poll_interval_seconds
        price_polls = owned_minutes * 60 // policy.price_poll_interval_seconds
        reconciliation_reserve = policy.maximum_reconciliation_pages * 3
        entry_reserve = policy.max_detail_get_calls + policy.maximum_entry_auxiliary_get_calls
        order_reserve = (
            policy.maximum_entry_attempts + policy.maximum_exit_attempts
        ) * reconciliation_reserve
        minimum_full_session_budget = (
            reconciliation_reserve
            + entry_reserve
            + position_polls * policy.maximum_reconciliation_pages
            + price_polls
            + order_reserve
        )

        self.assertGreaterEqual(policy.daily_get_budget, minimum_full_session_budget)
        self.assertEqual(policy.reconciliation_tick_deadline_seconds, 10)
    def test_manual_reconciliation_is_terminal_and_order_completion_is_exact(self) -> None:
        state = _state()
        intent = OrderIntent(symbol="QQQ", side=OrderSide.BUY, quantity=1, limit_price_usd=Decimal("19.50"))
        pending = state.record_intent(intent)

        completed = pending.complete_intent("KIS-123")
        terminal = completed.require_manual_reconciliation()

        self.assertEqual(completed.known_order.order_id, "KIS-123")
        with self.assertRaises(CanaryStateTransitionError):
            completed.clear_completed_order("KIS-999")
        with self.assertRaises(CanaryStateTransitionError):
            terminal.record_intent(intent)
    def test_arm_rejects_expired_or_binary_mismatched_envelope(self) -> None:
        expired = parse_arm_envelope(_envelope_payload(
            issued_at=datetime(2026, 7, 15, tzinfo=UTC), expires_at=datetime(2026, 7, 16, tzinfo=UTC)
        ))
        context = ArmValidationContext(
            market_date="2026-07-17", account_fingerprint="a" * 64, product="overseas_stock",
            base_url="https://openapi.koreainvestment.com:9443", executable_sha256="b" * 64,
            policy_digest=CANARY_POLICY.digest, windows_sid_sha256="b" * 64, now=datetime(2026, 7, 17, tzinfo=UTC),
        )

        with self.assertRaises(ArmEnvelopeError):
            validate_arm_envelope(expired, context)


    def test_arm_parses_only_complete_typed_envelopes(self) -> None:
        envelope = parse_arm_envelope(_envelope_payload(expires_at=datetime(2026, 7, 18, tzinfo=UTC)))

        validate_arm_envelope(envelope, ArmValidationContext(
            market_date="2026-07-17", account_fingerprint="a" * 64,
            product="overseas_stock",
            base_url="https://openapi.koreainvestment.com:9443",
            executable_sha256="a" * 64,
            policy_digest=CANARY_POLICY.digest, windows_sid_sha256="b" * 64,
            now=datetime(2026, 7, 17, tzinfo=UTC),
        ))

        self.assertEqual(envelope.state_nonce, "nonce-123")


    def test_identity_hashes_are_deterministic_and_do_not_expose_account_number(self) -> None:
        with self.subTest("hashes"):
            from tempfile import TemporaryDirectory
            with TemporaryDirectory() as temporary_directory:
                executable = Path(temporary_directory) / "canary.exe"
                executable.write_bytes(b"live-canary")

                fingerprint = account_fingerprint("12345678", "01")
                digest = executable_sha256(executable)

                self.assertEqual(fingerprint, "3c04892bc0b1fb8339ce70d2b674410e5aa1b7c6c23bf698e72006deaf68c7b4")
                self.assertNotIn("12345678", fingerprint)
                self.assertEqual(digest, "a7bd2592d0ff007407d5135ce9012f6ea31fc1c96d667cfd040b5f99d6b48b58")


    def test_fixed_policy_never_permits_more_than_one_share_or_twenty_dollars(self) -> None:
        policy = CANARY_POLICY

        self.assertEqual(policy.entry_limit_price_usd, Decimal("19.50"))
        self.assertEqual(policy.total_cash_gate_usd, Decimal("20.00"))
        self.assertEqual(policy.quantity, 1)


    def test_exit_only_rejects_every_buy_and_foreign_sell(self) -> None:
        state = _state(mode=StateMode.EXIT_ONLY)

        with self.assertRaises(CanaryStateTransitionError):
            state.record_intent(OrderIntent(symbol="QQQ", side=OrderSide.BUY, quantity=1))
        with self.assertRaises(CanaryStateTransitionError):
            state.record_intent(OrderIntent(symbol="SPY", side=OrderSide.SELL, quantity=1))
        with self.assertRaises(CanaryStateTransitionError):
            state.record_intent(OrderIntent(symbol="QQQ", side=OrderSide.SELL, quantity=2))


    def test_expired_arm_transitions_owned_state_to_exit_only(self) -> None:
        state = _state().with_owned_position("QQQ", 1)

        exit_only = state.expire_arm()

        self.assertIs(exit_only.mode, StateMode.EXIT_ONLY)
        self.assertEqual(exit_only.owned_symbol, "QQQ")


    def test_state_store_round_trips_atomically_and_binds_nonce_to_file(self) -> None:
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "live-canary-2026-07-17.json"
            store = CanaryStateStore(path)
            state = _state()

            store.save(state)
            loaded = CanaryStateStore(path).load(expected_nonce="nonce-123")

            self.assertEqual(loaded, state)
            with self.assertRaises(CanaryStateCorruptError):
                CanaryStateStore(path).load(expected_nonce="other-nonce")

    def test_cooldown_is_durable_across_restart(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "live-canary-2026-07-17.json"
            store = CanaryStateStore(path)
            state = _state().with_cooldown_until("2026-07-17T15:30:00+00:00")

            store.save(state)
            loaded = store.load(expected_nonce="nonce-123")

            self.assertEqual(loaded.cooldown_until, "2026-07-17T15:30:00+00:00")


    def test_state_store_fails_closed_on_corrupt_schema_or_redacted_secret(self) -> None:
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "live-canary-2026-07-17.json"
            path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")

            with self.assertRaises(CanaryStateCorruptError):
                CanaryStateStore(path).load(expected_nonce="nonce-123")

            path.write_text(json.dumps({"schema_version": 1, "access_token": "secret"}), encoding="utf-8")
            with self.assertRaises(CanaryStateCorruptError):
                CanaryStateStore(path).load(expected_nonce="nonce-123")


    def test_next_session_resets_sell_attempts_but_never_restores_buy_authority(self) -> None:
        state = CanaryState(
        market_date="2026-07-17",
        nonce="nonce-123",
        account_fingerprint="account:abc",
        executable_sha256="a" * 64,
        mode=StateMode.EXIT_ONLY,
        owned_symbol="QQQ",
        max_owned_quantity=1,
        round_trips=3,
        entry_attempts=3,
        exit_attempts=3,
        intent=None,
        )

        next_session = state.for_next_session("2026-07-20")

        self.assertIs(next_session.mode, StateMode.EXIT_ONLY)
        self.assertEqual(next_session.exit_attempts, 0)
        with self.assertRaises(CanaryStateTransitionError):
            next_session.record_intent(OrderIntent(symbol="QQQ", side=OrderSide.BUY, quantity=1))
