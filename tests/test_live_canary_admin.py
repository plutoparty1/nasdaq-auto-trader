from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from nasdaq_auto_trader.broker import KISCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.live_canary_admin import (
    ARM_CONFIRMATION,
    ArmIssueError,
    ArmIssueRequest,
    enforce_private_windows_acl,
    issue_arm,
)
from nasdaq_auto_trader.live_canary_arm import parse_arm_envelope
from nasdaq_auto_trader.live_canary_paths import CanaryPaths
from nasdaq_auto_trader.models import AccountSnapshot


class EmptyAccountClient:
    def get_account(self, refresh: bool = False):
        return AccountSnapshot(20.0, 20.0, 20.0)

    def list_positions(self, refresh: bool = False):
        return {}

    def list_open_orders(self):
        return ()


def _live_config() -> AppConfig:
    return AppConfig(
        mode="live",
        broker="kis",
        allow_live_trading=True,
        live_environment_authorized=True,
        kis=KISCredentials("app", "secret", "12345678", paper=False),
    )


class LiveCanaryAdminTests(unittest.TestCase):
    @patch("nasdaq_auto_trader.live_canary_admin._current_windows_sid", return_value="S-1-5-21-123")
    @patch("nasdaq_auto_trader.live_canary_admin.subprocess.run")
    def test_private_acl_keeps_root_private_then_resets_descendants(
        self,
        run_command: MagicMock,
        _sid: MagicMock,
    ) -> None:
        run_command.return_value.returncode = 0
        root = Path("C:/private/runtime")

        enforce_private_windows_acl(root)

        commands = [call.args[0] for call in run_command.call_args_list]
        self.assertEqual(
            commands,
            [
                [
                    "icacls", str(root), "/inheritance:r", "/grant:r",
                    "*S-1-5-21-123:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F",
                ],
                ["icacls", str(root / "*"), "/reset", "/T"],
            ],
        )

    def test_issue_arm_persists_bound_envelope_and_initial_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "canary.exe"
            executable.write_bytes(b"fixed executable")
            paths = CanaryPaths(Path(temp_dir) / "runtime", "2026-07-17")
            request = ArmIssueRequest(
                config=_live_config(),
                client=EmptyAccountClient(),
                paths=paths,
                executable=executable,
                market_date="2026-07-17",
                confirmation=ARM_CONFIRMATION,
                now=datetime(2026, 7, 17, 14, 0, tzinfo=UTC),
                windows_sid_sha256="a" * 64,
            )

            enforced_paths: list[Path] = []
            result = issue_arm(request, enforce_acl=enforced_paths.append)

            envelope = parse_arm_envelope(result.arm_payload)
            self.assertEqual(envelope.market_date, "2026-07-17")
            self.assertTrue(paths.arm.exists())
            self.assertTrue(paths.state.exists())
            self.assertNotIn("12345678", paths.arm.read_text(encoding="utf-8"))
            self.assertEqual(enforced_paths, [paths.root.parent])

    def test_issue_arm_enforces_acl_before_preflight_reads(self):
        events: list[str] = []

        class OrderedClient(EmptyAccountClient):
            def get_account(self, refresh: bool = False):
                events.append("preflight")
                return super().get_account(refresh)

        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "canary.exe"
            executable.write_bytes(b"fixed executable")
            paths = CanaryPaths(Path(temp_dir) / "runtime", "2026-07-17")
            request = ArmIssueRequest(
                config=_live_config(), client=OrderedClient(), paths=paths,
                executable=executable, market_date="2026-07-17",
                confirmation=ARM_CONFIRMATION,
                now=datetime(2026, 7, 17, 14, 0, tzinfo=UTC),
                windows_sid_sha256="a" * 64,
            )

            issue_arm(request, enforce_acl=lambda path: events.append("acl"))

        self.assertEqual(events[:2], ["acl", "preflight"])

    def test_issue_arm_rejects_wrong_confirmation_before_writes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "canary.exe"
            executable.write_bytes(b"fixed executable")
            paths = CanaryPaths(Path(temp_dir) / "runtime", "2026-07-17")
            request = ArmIssueRequest(
                config=_live_config(), client=EmptyAccountClient(), paths=paths,
                executable=executable, market_date="2026-07-17", confirmation="wrong",
                now=datetime(2026, 7, 17, 14, 0, tzinfo=UTC), windows_sid_sha256="a" * 64,
            )

            with self.assertRaises(ArmIssueError):
                issue_arm(request, enforce_acl=lambda path: None)

            self.assertFalse(paths.arm.exists())

    def test_issue_arm_cannot_reset_an_existing_market_date(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "canary.exe"
            executable.write_bytes(b"fixed executable")
            paths = CanaryPaths(Path(temp_dir) / "runtime", "2026-07-17")
            paths.root.mkdir(parents=True)
            paths.state.write_text("existing", encoding="utf-8")
            request = ArmIssueRequest(
                config=_live_config(), client=EmptyAccountClient(), paths=paths,
                executable=executable, market_date="2026-07-17", confirmation=ARM_CONFIRMATION,
                now=datetime(2026, 7, 17, 14, 0, tzinfo=UTC), windows_sid_sha256="a" * 64,
            )

            with self.assertRaisesRegex(ArmIssueError, "already exists"):
                issue_arm(request, enforce_acl=lambda path: None)

            self.assertEqual(paths.state.read_text(encoding="utf-8"), "existing")


if __name__ == "__main__":
    unittest.main()
