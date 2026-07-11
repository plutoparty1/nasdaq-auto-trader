import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.quant_data.market_quality import filter_tradeable_symbols
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.ai_quant_fixtures import bars
from tests.test_auto_symbol_live_guard import (
    _LiveBroker,
    _SecondWriteFailsAudit,
    _live_engine,
    _write_champion,
)


class AutoSymbolOrderTimeRecheckTests(unittest.TestCase):
    def test_nonfinite_older_history_bar_is_rejected_before_features(self):
        malformed = [*bars("AAPL")]
        malformed[-21] = replace(malformed[-21], close=float("nan"))

        result = filter_tradeable_symbols({"AAPL": malformed})

        self.assertEqual(result.symbols, ())
        self.assertIn("market_data_non_finite", result.rejected["AAPL"])

    def test_learned_risk_change_after_claim_blocks_before_broker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                NullAuditLogger(),
            )
            broker = _LiveBroker("accepted")
            engine = _live_engine(paths, guard, broker)
            original_begin = guard.begin

            def change_risk_after_begin(context, order, now):
                permit = original_begin(context, order, now)
                paths.ai_config_path.write_text(
                    json.dumps({"max_order_notional": 250}),
                    encoding="utf-8",
                )
                return permit

            guard.begin = change_risk_after_begin

            results = engine.run_once()

        self.assertEqual(broker.orders, [])
        self.assertTrue(
            any(
                item["response"]["reason"]
                == "live_authorization_binding_changed"
                for item in results
            )
        )

    def test_terminal_outcome_failure_stops_cycle_after_accepted_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir) / "artifacts")
            _write_champion(paths)
            spec_path = paths.spec_dir / "auto-v1.json"
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            spec["entry_rule"]["top_n"] = 2
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            guard = AutomaticOrderGuard(
                paths,
                TradingSessionStore(Path(temp_dir) / "session.json"),
                _SecondWriteFailsAudit(),
            )
            broker = _LiveBroker("accepted")
            engine = _live_engine(paths, guard, broker)

            results = engine.run_once()

        self.assertEqual(len(broker.orders), 1)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["response"]["broker_submitted"])
        self.assertTrue(results[0]["response"]["terminal"])


if __name__ == "__main__":
    unittest.main()
