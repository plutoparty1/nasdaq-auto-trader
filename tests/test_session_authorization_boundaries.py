import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.automatic_order_types import AutomaticOrderBlock
from nasdaq_auto_trader.live_authorization import (
    LiveAuthorizationBlock,
    LiveAuthorizationEnvelope,
    LiveAuthorizationRequest,
    create_live_authorization,
)
from nasdaq_auto_trader.models import OrderRequest
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.test_auto_symbol_authorization_risk import _context, _live_app_config
from tests.test_auto_symbol_live_guard import _write_champion


class SessionAuthorizationBoundaryTests(unittest.TestCase):
    def test_naive_order_time_blocks_without_consuming_attempt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            guard, authorization, now = _guard(Path(temp_dir), hour=14, minute=30)

            blocked = guard.begin(
                _context(authorization),
                OrderRequest("AAPL", "buy", qty=1),
                datetime(2026, 7, 13, 14, 30),
            )
            stored = guard.authorization_store.load()

        self.assertIsInstance(blocked, AutomaticOrderBlock)
        self.assertEqual(blocked.reason, "market_time_timezone_required")
        self.assertEqual(stored.attempts, 0)
        self.assertEqual(now.tzinfo, timezone.utc)

    def test_confirm_at_market_close_rejects_existing_permit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            guard, authorization, now = _guard(
                Path(temp_dir),
                hour=19,
                minute=59,
                second=59,
            )
            order = OrderRequest("AAPL", "buy", qty=1)

            permit = guard.begin(_context(authorization), order, now)
            self.assertNotIsInstance(permit, AutomaticOrderBlock)
            blocked = guard.confirm(
                permit,
                order,
                datetime(2026, 7, 13, 20, 0, tzinfo=timezone.utc),
            )

        self.assertIsInstance(blocked, AutomaticOrderBlock)
        self.assertEqual(
            blocked.reason,
            "live_authorization_outside_regular_session",
        )

    def test_next_market_date_blocks_without_consuming_attempt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            guard, authorization, _ = _guard(Path(temp_dir), hour=14, minute=30)

            blocked = guard.begin(
                _context(authorization),
                OrderRequest("AAPL", "buy", qty=1),
                datetime(2026, 7, 14, 14, 30, tzinfo=timezone.utc),
            )
            stored = guard.authorization_store.load()

        self.assertIsInstance(blocked, AutomaticOrderBlock)
        self.assertEqual(
            blocked.reason,
            "live_authorization_market_date_mismatch",
        )
        self.assertEqual(stored.attempts, 0)


def _guard(
    root: Path,
    *,
    hour: int,
    minute: int,
    second: int = 0,
) -> tuple[AutomaticOrderGuard, LiveAuthorizationEnvelope, datetime]:
    paths = StrategyArtifactPaths.from_root(root)
    _write_champion(paths)
    now = datetime(2026, 7, 13, hour, minute, second, tzinfo=timezone.utc)
    authorization = create_live_authorization(
        LiveAuthorizationRequest(_live_app_config(), paths, now, 2)
    )
    if isinstance(authorization, LiveAuthorizationBlock):
        raise AssertionError(authorization.reason)
    guard = AutomaticOrderGuard(
        paths,
        TradingSessionStore(root / "session.json"),
        NullAuditLogger(),
        broker_authorization_digest=authorization.broker_authorization_digest,
    )
    guard.authorization_store.issue(authorization)
    if guard.start_cycle(now):
        raise AssertionError("authorization must load")
    return guard, authorization, now


if __name__ == "__main__":
    unittest.main()
