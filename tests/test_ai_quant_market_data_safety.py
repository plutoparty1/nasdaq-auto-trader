import json
import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.operator_market_data import (
    BarsJsonError,
    load_bars_json,
)


class AIQuantMarketDataSafetyTests(unittest.TestCase):
    def test_bars_json_rejects_infinite_number(self):
        payload = {
            "QQQ": [
                {
                    "timestamp": "2026-07-10",
                    "open": float("inf"),
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1_000_000.0,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bars.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(BarsJsonError) as raised:
                load_bars_json(path)

        self.assertEqual(str(raised.exception), "bars_json_open_must_be_number")


if __name__ == "__main__":
    unittest.main()
