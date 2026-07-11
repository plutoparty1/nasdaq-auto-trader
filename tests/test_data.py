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


if __name__ == "__main__":
    unittest.main()
