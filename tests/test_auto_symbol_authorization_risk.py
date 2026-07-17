import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import nasdaq_auto_trader.cli as cli_module
from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.automatic_order_types import (
    AutomaticOrderBlock,
    AutomaticOrderContext,
)
from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.cli import main
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSessionState, TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.live_authorization import (
    LiveAuthorizationBlock,
    LiveAuthorizationRequest,
    create_live_authorization,
)
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest
from nasdaq_auto_trader.risk import RiskConfig
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.config_engine_fixtures import compact_strategy_config
from tests.test_auto_symbol_engine import (
    _AcceptedBroker,
    _AutoMarketData,
    _write_paper_strategy,
)
from tests.test_auto_symbol_live_guard import _write_champion


class AutoSymbolAuthorizationRiskTests(unittest.TestCase):
    def test_cli_bounds_are_passed_to_order_time_authorization(self):
        engines = []

        class FakeEngine:
            def __init__(self, *args, **kwargs):
                del args
                engines.append(kwargs)
                self.last_selection_report = None

            def run_once(self):
                return []

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = _live_config(Path(temp_dir))
            output = io.StringIO()
            with patch.object(cli_module, "TradingEngine", FakeEngine):
                with redirect_stdout(output):
                    main(
                        [
                            "--config",
                            str(config_path),
                            "loop",
                            "--auto-select",
                            "--confirm-live-orders",
                            "--live-auth-minutes",
                            "5",
                            "--live-max-cycles",
                            "2",
                            "--interval-minutes",
                            "1",
                            "--max-runs",
                            "1",
                        ]
                    )

        self.assertEqual(engines[0]["live_authorization_duration_minutes"], 5)
        self.assertEqual(engines[0]["live_authorization_max_cycles"], 2)

    def test_authorization_binds_universe_checksum_and_enforces_expiry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_champion(paths)
            now = datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)
            config = _live_app_config()
            authorization = create_live_authorization(
                LiveAuthorizationRequest(config, paths, now, 1, 1)
            )
            self.assertNotIsInstance(authorization, LiveAuthorizationBlock)
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                NullAuditLogger(),
            )
            guard.set_live_authorization(authorization)
            self.assertEqual(guard.start_cycle(now), "")
            context = _context(authorization)

            expired = guard.begin(
                context,
                OrderRequest("AAPL", "buy", qty=1),
                now + timedelta(minutes=2),
            )

        self.assertIsInstance(expired, AutomaticOrderBlock)
        self.assertEqual(expired.reason, "live_authorization_expired")
        self.assertTrue(authorization.universe_version.startswith("sha256:"))

    def test_authorization_cycle_budget_blocks_second_cycle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_champion(paths)
            now = datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)
            authorization = create_live_authorization(
                LiveAuthorizationRequest(_live_app_config(), paths, now, 5, 1)
            )
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                NullAuditLogger(),
            )
            guard.set_live_authorization(authorization)

            first = guard.start_cycle(now)
            second = guard.start_cycle(now + timedelta(seconds=1))

        self.assertEqual(first, "")
        self.assertEqual(second, "live_authorization_cycle_limit_reached")

    def test_automatic_cycle_applies_learned_total_exposure_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_paper_strategy(paths, top_n=2)
            paths.ai_config_path.write_text(
                json.dumps(
                    {
                        "max_single_position_pct": 0.05,
                        "max_total_exposure_pct": 0.03,
                        "max_order_notional": 1000,
                        "max_orders_per_day": 5,
                    }
                ),
                encoding="utf-8",
            )
            broker = _AcceptedBroker()
            engine = TradingEngine(
                AppConfig(
                    mode="dry_run",
                    strategy=compact_strategy_config(),
                    risk=RiskConfig(order_qty=1, max_position_qty=10),
                ),
                broker=broker,
                market_data=_AutoMarketData(
                    account=AccountSnapshot(10_000, 10_000, 10_000)
                ),
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                    max_daily_buy_count=10,
                    max_position_qty=10,
                    require_confirm_before_buy=False,
                ),
                trading_session_state=TradingSessionState(),
                strategy_artifact_paths=paths,
            )

            results = engine.run_once()

        self.assertEqual(broker.orders, [])
        self.assertTrue(
            any(
                item["response"] is not None
                and item["response"].get("status") == "dry_run"
                for item in results
            )
        )
        self.assertTrue(
            any(
                item["response"] is not None
                and item["response"].get("reason")
                == "learned_total_exposure_limit_reached"
                for item in results
            )
        )


def _context(authorization) -> AutomaticOrderContext:
    return AutomaticOrderContext(
        strategy_id=authorization.strategy_id,
        strategy_version=authorization.strategy_version,
        strategy_digest=authorization.strategy_digest,
        universe_id=authorization.universe_id,
        universe_effective_date=authorization.universe_effective_date,
        universe_version=authorization.universe_version,
        risk_digest=authorization.risk_digest,
        mode=authorization.mode,
        signal_timestamp="2026-07-13T14:29:00+00:00",
        max_daily_buy_count=5,
        max_daily_sell_count=5,
        max_daily_order_count=5,
        learned_risk_digest=authorization.learned_risk_digest,
        cooldown_minutes=0,
        daily_loss_breached=False,
        daily_loss_state_unavailable=False,
        baseline_available=True,
    )


def _live_app_config() -> AppConfig:
    return AppConfig(
        mode="live",
        allow_live_trading=True,
        live_environment_authorized=True,
        regular_market_hours_only=False,
        alpaca=AlpacaCredentials("key", "secret", paper=False),
    )


def _live_config(root: Path) -> Path:
    path = root / "config.json"
    path.write_text(
        json.dumps(
            {
                "mode": "live",
                "allow_live_trading": True,
                "regular_market_hours_only": False,
                "alpaca": {
                    "api_key": "key",
                    "secret_key": "secret",
                    "paper": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (root / ".env").write_text(
        "NASDAQ_AUTO_TRADER_ALLOW_LIVE=YES\n",
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    unittest.main()
