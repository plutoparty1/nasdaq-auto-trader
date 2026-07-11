import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nasdaq_auto_trader.cli_formatters import automatic_cycle_to_dict
from nasdaq_auto_trader.quant_data.selection_cache import SelectionCache
from tests.test_auto_symbol_safety_regressions import _Decision, _identity, _report


class AutoSymbolOutputCacheContractTests(unittest.TestCase):
    def test_cache_rejects_coherent_non_universe_rank_tampering(self):
        identity = _identity()
        report = _report()
        now = datetime(2026, 7, 14, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "latest.json"
            cache = SelectionCache(path, timedelta(minutes=15))
            cache.write(identity, report, now)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["report"]["ranked"][0]["symbol"] = "ZZZZ"
            payload["report"]["selected_symbols"] = ["ZZZZ"]
            path.write_text(json.dumps(payload), encoding="utf-8")

            loaded = cache.read(identity, now)

        self.assertIsNone(loaded)

    def test_mixed_terminal_cycle_preserves_prior_submitted_order_truth(self):
        payload = automatic_cycle_to_dict(
            _report(),
            [
                {
                    "symbol": "AAPL",
                    "decision": _Decision(),
                    "response": {"status": "accepted", "id": "1"},
                },
                {
                    "symbol": "MSFT",
                    "decision": _Decision(),
                    "response": {
                        "status": "blocked",
                        "reason": "live_authorization_expired",
                        "terminal": True,
                    },
                },
            ],
        )

        self.assertTrue(payload["submitted_order"])

    def test_kis_success_response_reports_submitted_order(self):
        payload = automatic_cycle_to_dict(
            _report(),
            [
                {
                    "symbol": "AAPL",
                    "decision": _Decision(),
                    "response": {"rt_cd": "0", "msg1": "accepted"},
                }
            ],
        )

        self.assertTrue(payload["submitted_order"])


if __name__ == "__main__":
    unittest.main()
