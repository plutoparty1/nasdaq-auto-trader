import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.live_authorization_store import (
    LiveAuthorizationStore,
    LiveAuthorizationStoreError,
)
from nasdaq_auto_trader.live_session_authorization import (
    LIVE_SESSION_CONFIRMATION,
    SessionAuthorizationRequest,
    authorize_live_session,
    revoke_live_session,
)
from tests.config_engine_fixtures import compact_strategy_config
from tests.test_auto_symbol_live_guard import _write_champion
from tests.test_session_live_authorization import SESSION_OPEN, _envelope


class SessionLiveAuthorizationFailureTests(unittest.TestCase):
    def test_authorization_audit_failure_preserves_existing_authority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_champion(paths)
            store = LiveAuthorizationStore(root / "authorization.json")
            existing = _envelope("1" * 32)
            store.issue(existing)
            audit = NullAuditLogger()
            audit.fail_writes = True

            result = authorize_live_session(
                _authorization_request(paths, store, audit)
            )
            stored = store.load()

        self.assertEqual(
            result["reason"],
            "live_authorization_audit_write_failed",
        )
        self.assertEqual(stored.envelope, existing)

    def test_write_failure_after_archive_leaves_no_active_authority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_champion(paths)
            store = LiveAuthorizationStore(root / "authorization.json")
            store.issue(_envelope("1" * 32))
            audit = NullAuditLogger()

            with patch.object(
                store,
                "_write_unlocked",
                side_effect=LiveAuthorizationStoreError(
                    "live_authorization_store_write_failed"
                ),
            ):
                result = authorize_live_session(
                    _authorization_request(paths, store, audit)
                )

            archives = list(root.glob("authorization.json.archive-*"))

        self.assertEqual(
            result["reason"],
            "live_authorization_store_write_failed",
        )
        self.assertFalse(store.path.exists())
        self.assertEqual(len(archives), 1)
        self.assertEqual(
            [event.event_type for event in audit.events],
            ["live_authorization_session_approval_requested"],
        )

    def test_revoke_store_failure_does_not_audit_completed_revocation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = LiveAuthorizationStore(root / "authorization.json")
            store.issue(_envelope("1" * 32))
            audit = NullAuditLogger()

            with patch.object(
                store,
                "clear",
                side_effect=LiveAuthorizationStoreError(
                    "live_authorization_store_write_failed"
                ),
            ):
                result = revoke_live_session(store, audit)

            stored = store.load()

        self.assertEqual(result["reason"], "live_authorization_store_write_failed")
        self.assertIsNotNone(stored)
        self.assertEqual(
            [event.event_type for event in audit.events],
            ["live_authorization_session_revocation_requested"],
        )

    def test_completion_audit_failure_reports_active_authorization_truthfully(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = StrategyArtifactPaths.from_root(root / "artifacts")
            _write_champion(paths)
            store = LiveAuthorizationStore(root / "authorization.json")
            audit = _SecondWriteFailsAudit()

            result = authorize_live_session(
                _authorization_request(paths, store, audit)
            )
            stored = store.load()

        self.assertEqual(result["status"], "authorized")
        self.assertFalse(result["audit_completion_recorded"])
        self.assertIsNotNone(stored)

    def test_revoke_completion_audit_failure_reports_revoked_truthfully(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LiveAuthorizationStore(Path(temp_dir) / "authorization.json")
            store.issue(_envelope("1" * 32))

            result = revoke_live_session(store, _SecondWriteFailsAudit())
            stored = store.load()

        self.assertEqual(result["status"], "revoked")
        self.assertFalse(result["audit_completion_recorded"])
        self.assertIsNone(stored)

    def test_revoke_archive_failure_reports_revoked_with_cleanup_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LiveAuthorizationStore(Path(temp_dir) / "authorization.json")
            store.issue(_envelope("1" * 32))
            audit = NullAuditLogger()

            with patch.object(
                store,
                "_archive_unlocked",
                side_effect=LiveAuthorizationStoreError(
                    "live_authorization_store_write_failed"
                ),
            ):
                result = revoke_live_session(store, audit)

            stored = store.load()

        self.assertEqual(result["status"], "revoked")
        self.assertFalse(result["revocation_cleanup_completed"])
        self.assertIsNone(stored)


def _authorization_request(
    paths: StrategyArtifactPaths,
    store: LiveAuthorizationStore,
    audit: NullAuditLogger,
) -> SessionAuthorizationRequest:
    config = AppConfig(
        mode="live",
        allow_live_trading=True,
        live_environment_authorized=True,
        alpaca=AlpacaCredentials("key", "secret", paper=False),
        strategy=compact_strategy_config(),
    )
    return SessionAuthorizationRequest(
        config=config,
        paths=paths,
        store=store,
        audit=audit,
        now=SESSION_OPEN,
        max_attempts=12,
        confirmation=LIVE_SESSION_CONFIRMATION,
    )


class _SecondWriteFailsAudit:
    def __init__(self) -> None:
        self.calls = 0

    def append(self, event) -> bool:
        del event
        self.calls += 1
        return self.calls == 1


if __name__ == "__main__":
    unittest.main()
