import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.automatic_selection import AutomaticSelectionRequest
from nasdaq_auto_trader.automatic_selection_production import _cache_identity
from nasdaq_auto_trader.cli_formatters import automatic_cycle_to_dict
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.quant_data.market_quality import filter_tradeable_symbols
from nasdaq_auto_trader.quant_data.selection_cache import (
    SelectionCache,
    SelectionCacheIdentity,
)
from nasdaq_auto_trader.quant_data.symbol_selector import (
    RankedSymbol,
    ResolvedStrategy,
    SelectionReport,
    resolve_strategy,
)
from nasdaq_auto_trader.quant_data.universe_snapshot import load_default_universe
from nasdaq_auto_trader.trading_session_store import (
    PersistedSafetyState,
    SafetyReservationRequest,
    SessionStoreError,
    TradingSessionStore,
)
from tests.ai_quant_fixtures import bars
from tests.test_auto_symbol_engine import _AutoMarketData, _write_paper_strategy
from tests.test_auto_symbol_live_guard import (
    _LiveBroker,
    _live_engine,
    _write_champion,
)


class AutoSymbolSafetyRegressionTests(unittest.TestCase):
    def test_stale_process_cannot_roll_back_newer_market_date(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TradingSessionStore(Path(temp_dir) / "session.json")
            store.save_safety_state(
                PersistedSafetyState(market_date="2026-07-14", buy_count=1)
            )

            store.merge_safety_state(
                PersistedSafetyState(market_date="2026-07-13", buy_count=0)
            )
            decision = store.reserve_safety(_reservation("2026-07-14"))
            persisted = store.load_safety_state()

        self.assertEqual(persisted.market_date, "2026-07-14")
        self.assertEqual(persisted.buy_count, 1)
        self.assertFalse(decision.granted)
        self.assertEqual(decision.reason, "max_daily_buy_count_reached")

    def test_semantically_corrupt_safety_fields_fail_closed(self):
        invalid_safety = (
            {"market_date": "2026-07-14", "buy_count": -1},
            {"market_date": "2026-07-14", "buy_count": True},
            {"market_date": "2026-07-14", "daily_loss_breached": 1},
            {"market_date": "not-a-date"},
            {"market_date": "2026-07-14", "last_order_at": "not-a-time"},
        )
        for safety in invalid_safety:
            with self.subTest(safety=safety), tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "session.json"
                payload = {
                    "schema_version": 1,
                    "safety": {
                        "market_date": "",
                        "buy_count": 0,
                        "sell_count": 0,
                        "last_order_at": "",
                        "daily_loss_breached": False,
                        "baseline_observed": False,
                        **safety,
                    },
                    "claims": {},
                }
                path.write_text(json.dumps(payload), encoding="utf-8")

                with self.assertRaises(SessionStoreError) as raised:
                    TradingSessionStore(path).load_safety_state()

                self.assertEqual(raised.exception.reason, "session_store_corrupt")

    def test_nonfinite_or_invalid_ohlcv_is_rejected(self):
        variants = (
            {"volume": float("nan")},
            {"close": float("inf")},
            {"open": float("-inf")},
            {"volume": -1.0},
            {"high": 1.0, "low": 2.0},
        )
        for changes in variants:
            with self.subTest(changes=changes):
                malformed = [*bars("AAPL")]
                malformed[-1] = replace(malformed[-1], **changes)

                result = filter_tradeable_symbols({"AAPL": malformed})

                self.assertEqual(result.symbols, ())
                self.assertIn("AAPL", result.rejected)

    def test_cache_rejects_semantically_tampered_selected_symbols(self):
        identity = _identity()
        report = _report()
        now = datetime(2026, 7, 14, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "latest.json"
            cache = SelectionCache(path, timedelta(minutes=15))
            cache.write(identity, report, now)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["report"]["selected_symbols"] = ["ZZZZ"]
            path.write_text(json.dumps(payload), encoding="utf-8")

            loaded = cache.read(identity, now)

        self.assertIsNone(loaded)

    def test_cache_identity_changes_with_promoted_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_paper_strategy(paths)
            request = AutomaticSelectionRequest(
                AppConfig(mode="paper"),
                _AutoMarketData(),
                paths,
                datetime(2026, 7, 14, tzinfo=timezone.utc),
            )
            resolved = resolve_strategy("paper", paths)
            self.assertIsInstance(resolved, ResolvedStrategy)
            first = _cache_identity(request, load_default_universe(), resolved)
            paths.promoted_path.write_text(
                json.dumps({"status": "rollback", "mode": "no_trade"}),
                encoding="utf-8",
            )

            second = _cache_identity(request, load_default_universe(), resolved)

        self.assertNotEqual(first, second)

    def test_terminal_reconciliation_reports_accepted_broker_order(self):
        payload = automatic_cycle_to_dict(
            _report(),
            [
                {
                    "symbol": "AAPL",
                    "decision": _Decision(),
                    "response": {
                        "status": "blocked",
                        "reason": "order_outcome_audit_failed_reconcile_required",
                        "terminal": True,
                        "broker_submitted": True,
                    },
                }
            ],
        )

        self.assertTrue(payload["submitted_order"])

    def test_rollback_after_claim_is_rechecked_before_broker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            broker = _LiveBroker("accepted")
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                NullAuditLogger(),
            )
            engine = _live_engine(paths, guard, broker)
            guard = engine.automatic_order_guard
            original_begin = guard.begin

            def rollback_after_begin(context, order, now):
                permit = original_begin(context, order, now)
                paths.promoted_path.write_text(
                    json.dumps({"status": "rollback", "mode": "no_trade"}),
                    encoding="utf-8",
                )
                return permit

            guard.begin = rollback_after_begin

            results = engine.run_once()

        self.assertEqual(broker.orders, [])
        self.assertTrue(
            any(
                item["response"]["reason"] == "promoted_strategy_rollback"
                for item in results
            )
        )


class _Decision:
    action = "buy"
    score = 1


def _reservation(market_date: str) -> SafetyReservationRequest:
    return SafetyReservationRequest(
        market_date=market_date,
        side="buy",
        timestamp=f"{market_date}T14:30:00+00:00",
        max_daily_buy_count=1,
        max_daily_sell_count=1,
        cooldown_minutes=0,
        daily_loss_breached=False,
        daily_loss_state_unavailable=False,
        baseline_available=True,
    )


def _identity() -> SelectionCacheIdentity:
    return SelectionCacheIdentity(
        provider="alpaca",
        mode="paper",
        universe_id="nasdaq_100",
        universe_version="sha256:universe",
        universe_effective_date="2026-07-10",
        strategy_id="alpha",
        strategy_version="v1",
        strategy_digest="strategy-digest",
        registry_digest="registry-digest",
        promoted_digest="promoted-digest",
        market_date="2026-07-14",
        shortlist_limit=30,
    )


def _report() -> SelectionReport:
    ranked = RankedSymbol("AAPL", 1.0, 0.9, ("momentum",))
    return SelectionReport(
        status="selected",
        universe_id="nasdaq_100",
        universe_effective_date="2026-07-10",
        strategy_id="alpha",
        strategy_version="v1",
        strategy_digest="strategy-digest",
        shortlist_count=1,
        ranked=(ranked,),
        selected_symbols=("AAPL",),
        universe_version="sha256:universe",
    )


if __name__ == "__main__":
    unittest.main()
