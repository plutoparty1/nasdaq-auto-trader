import json
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import date, datetime, timezone
from multiprocessing import get_context
from pathlib import Path
from unittest.mock import patch

import nasdaq_auto_trader.live_authorization as authorization_model
from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.live_authorization_store import (
    LiveAuthorizationStore,
    LiveAuthorizationStoreError,
)
from nasdaq_auto_trader.trading_session_store import TradingSessionStore


SESSION_OPEN = datetime(2026, 8, 11, 14, 30, tzinfo=timezone.utc)


class SessionLiveAuthorizationTests(unittest.TestCase):
    def test_revocation_marker_overrides_stale_authorization_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "authorization.json"
            store = LiveAuthorizationStore(path)
            envelope = _envelope("1" * 32)
            store.issue(envelope)
            store.revoked_path.write_text("revoked\n", encoding="utf-8")

            loaded = store.load()
            reason, attempts = store.consume_attempt(envelope)
            validation = store.validate_current(envelope)

        self.assertIsNone(loaded)
        self.assertEqual(reason, "live_authorization_required")
        self.assertEqual(attempts, 0)
        self.assertEqual(validation, "live_authorization_required")

    def test_failed_explicit_reissue_keeps_revocation_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LiveAuthorizationStore(Path(temp_dir) / "authorization.json")
            store.clear()

            with patch.object(
                store,
                "_write_unlocked",
                side_effect=OSError("simulated write failure"),
            ):
                with self.assertRaises(LiveAuthorizationStoreError):
                    store.issue(_envelope("1" * 32))

            revoked = store.revoked_path.exists()

        self.assertTrue(revoked)

    def test_failed_archive_during_revoke_still_leaves_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LiveAuthorizationStore(Path(temp_dir) / "authorization.json")
            store.issue(_envelope("1" * 32))

            with patch.object(
                store,
                "_archive_unlocked",
                side_effect=OSError("simulated archive failure"),
            ):
                cleanup_completed = store.clear(archive=True)

            revoked = store.revoked_path.exists()

        self.assertTrue(revoked)
        self.assertFalse(cleanup_completed)

    def test_unlimited_automatic_authorization_allows_more_than_twelve_attempts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "authorization.json"
            envelope = _envelope("1" * 32, max_attempts=0)
            store = LiveAuthorizationStore(path)
            store.issue(envelope)

            outcomes = [store.consume_attempt(envelope) for _ in range(20)]
            stored = store.load()

        self.assertEqual([reason for reason, _ in outcomes], [""] * 20)
        self.assertEqual(stored.attempts, 20)

    def test_independent_store_instances_never_exceed_twelve_attempts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "authorization.json"
            envelope = _envelope("1" * 32)
            LiveAuthorizationStore(path).issue(envelope)

            with ThreadPoolExecutor(max_workers=20) as executor:
                outcomes = list(
                    executor.map(
                        lambda _: LiveAuthorizationStore(path).consume_attempt(envelope),
                        range(20),
                    )
                )
            stored = LiveAuthorizationStore(path).load()

        self.assertEqual(sum(reason == "" for reason, _ in outcomes), 12)
        self.assertEqual(
            sum(
                reason == "live_authorization_attempt_limit_reached"
                for reason, _ in outcomes
            ),
            8,
        )
        self.assertEqual(stored.attempts, 12)

    def test_independent_processes_never_exceed_twelve_attempts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "authorization.json"
            envelope = _envelope("1" * 32)
            LiveAuthorizationStore(path).issue(envelope)

            with ProcessPoolExecutor(
                max_workers=4,
                mp_context=get_context("spawn"),
            ) as executor:
                outcomes = list(
                    executor.map(
                        _consume_attempt_in_process,
                        [(path, envelope)] * 20,
                    )
                )
            stored = LiveAuthorizationStore(path).load()

        self.assertEqual(outcomes.count(""), 12)
        self.assertEqual(
            outcomes.count("live_authorization_attempt_limit_reached"),
            8,
        )
        self.assertEqual(stored.attempts, 12)

    def test_schema_two_round_trip_preserves_attempts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LiveAuthorizationStore(Path(temp_dir) / "authorization.json")
            envelope = _envelope("1" * 32, max_attempts=2)

            store.issue(envelope)
            reason, attempts = store.consume_attempt(envelope)
            reopened = LiveAuthorizationStore(store.path).load()

        self.assertEqual(reason, "")
        self.assertEqual(attempts, 1)
        self.assertEqual(reopened.envelope, envelope)
        self.assertEqual(reopened.attempts, 1)

    def test_start_cycle_reload_does_not_consume_attempt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_store = TradingSessionStore(root / "session.json")
            authorization_store = LiveAuthorizationStore(
                root / "session.live-authorization.json"
            )
            authorization_store.issue(_envelope("1" * 32))
            guard = AutomaticOrderGuard(
                StrategyArtifactPaths.from_root(root / "artifacts"),
                session_store,
                NullAuditLogger(),
                authorization_store,
                broker_authorization_digest="broker-digest",
            )

            reasons = [guard.start_cycle(SESSION_OPEN) for _ in range(78)]
            stored = authorization_store.load()

        self.assertEqual(set(reasons), {""})
        self.assertEqual(stored.attempts, 0)

    def test_running_guard_hot_reloads_external_authorize_and_revoke(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            authorization_store = LiveAuthorizationStore(
                root / "authorization.json"
            )
            guard = AutomaticOrderGuard(
                StrategyArtifactPaths.from_root(root / "artifacts"),
                TradingSessionStore(root / "session.json"),
                NullAuditLogger(),
                authorization_store,
                broker_authorization_digest="broker-digest",
            )

            before = guard.start_cycle(SESSION_OPEN)
            authorization_store.issue(_envelope("1" * 32))
            after_authorize = guard.start_cycle(SESSION_OPEN)
            stored = authorization_store.load()
            authorization_store.clear(archive=True)
            after_revoke = guard.start_cycle(SESSION_OPEN)

        self.assertEqual(before, "live_authorization_required")
        self.assertEqual(after_authorize, "")
        self.assertEqual(stored.attempts, 0)
        self.assertEqual(after_revoke, "live_authorization_required")

    def test_schema_one_requires_explicit_reapproval(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "authorization.json"
            path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
            guard = AutomaticOrderGuard(
                StrategyArtifactPaths.from_root(root / "artifacts"),
                TradingSessionStore(root / "session.json"),
                NullAuditLogger(),
                LiveAuthorizationStore(path),
                broker_authorization_digest="broker-digest",
            )

            reason = guard.start_cycle(SESSION_OPEN)

        self.assertEqual(reason, "live_authorization_reapproval_required")

    def test_guard_without_broker_binding_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            authorization_store = LiveAuthorizationStore(
                root / "authorization.json"
            )
            authorization_store.issue(_envelope("1" * 32))
            guard = AutomaticOrderGuard(
                StrategyArtifactPaths.from_root(root / "artifacts"),
                TradingSessionStore(root / "session.json"),
                NullAuditLogger(),
                authorization_store,
            )

            reason = guard.start_cycle(SESSION_OPEN)

        self.assertEqual(
            reason,
            "live_authorization_broker_binding_required",
        )

    def test_reissued_same_binding_has_a_new_generation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LiveAuthorizationStore(Path(temp_dir) / "authorization.json")
            first = _envelope("1" * 32)
            second = _envelope("2" * 32)
            store.issue(first)

            store.issue(second)
            reason = store.validate_current(first)

        self.assertEqual(reason, "live_authorization_binding_changed")


def _envelope(
    authorization_id: str,
    *,
    max_attempts: int = 12,
) -> authorization_model.LiveAuthorizationEnvelope:
    return authorization_model.LiveAuthorizationEnvelope(
        authorization_id=authorization_id,
        market_date=date(2026, 8, 11),
        max_attempts=max_attempts,
        strategy_id="strategy",
        strategy_version="v1",
        strategy_digest="strategy-digest",
        universe_id="nasdaq-100",
        universe_effective_date="2026-08-10",
        universe_version="universe-digest",
        risk_digest="risk-digest",
        mode="live",
        learned_risk_digest="learned-digest",
        broker_authorization_digest="broker-digest",
    )


def _consume_attempt_in_process(
    args: tuple[Path, authorization_model.LiveAuthorizationEnvelope],
) -> str:
    path, envelope = args
    reason, _ = LiveAuthorizationStore(path).consume_attempt(envelope)
    return reason


if __name__ == "__main__":
    unittest.main()
