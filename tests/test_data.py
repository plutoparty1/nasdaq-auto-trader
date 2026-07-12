import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.data import MissingCsvColumnsError, load_bars_csv


class DataLoadingTests(unittest.TestCase):
    def test_load_bars_csv_reports_typed_error_for_missing_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "bars.csv"
            csv_path.write_text(
                "symbol,timestamp,open,high,low,close\nQQQ,T001,1,2,0.5,1.5\n",
                encoding="utf-8",
            )

            with self.assertRaises(MissingCsvColumnsError) as context:
                load_bars_csv(csv_path)

        self.assertEqual(context.exception.missing_columns, ("volume",))
        self.assertEqual(str(context.exception), "missing CSV columns: volume")

    def test_load_bars_csv_accepts_bom_and_sorts_offsets_chronologically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "bars.csv"
            csv_path.write_text(
                (
                    "symbol,timestamp,open,high,low,close,volume\n"
                    "QQQ,2026-01-01T00:30:00+00:00,101,102,100,101,1000\n"
                    "QQQ,2026-01-01T01:00:00+02:00,100,101,99,100,1000\n"
                ),
                encoding="utf-8-sig",
            )

            bars = load_bars_csv(csv_path)["QQQ"]

        self.assertEqual([bar.close for bar in bars], [100, 101])

    def test_load_bars_csv_rejects_empty_duplicate_and_invalid_rows(self):
        cases = [
            ("symbol,timestamp,open,high,low,close,volume\n", "at least one"),
            (
                "symbol,timestamp,open,high,low,close,volume\n"
                "QQQ,2026-01-01,100,101,99,100,1\n"
                "QQQ,2026-01-01,100,101,99,100,1\n",
                "duplicate",
            ),
            (
                "symbol,timestamp,open,high,low,close,volume\n"
                ",2026-01-01,100,101,99,100,1\n",
                "symbol",
            ),
            (
                "symbol,timestamp,open,high,low,close,volume\n"
                "QQQ,not-a-time,100,101,99,100,1\n",
                "timestamp",
            ),
            (
                "symbol,timestamp,open,high,low,close,volume\n"
                "QQQ,2026-01-01,100,101,99,NaN,1\n",
                "close",
            ),
            (
                "symbol,timestamp,open,high,low,close,volume\n"
                "QQQ,2026-01-01,100,90,110,100,1\n",
                "high",
            ),
            (
                "symbol,timestamp,open,high,low,close,volume\n"
                "QQQ,2026-01-01,100,101,99,100,-1\n",
                "volume",
            ),
        ]

        for contents, pattern in cases:
            with self.subTest(pattern=pattern), tempfile.TemporaryDirectory() as temp_dir:
                csv_path = Path(temp_dir) / "bars.csv"
                csv_path.write_text(contents, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, pattern):
                    load_bars_csv(csv_path)


if __name__ == "__main__":
    unittest.main()
