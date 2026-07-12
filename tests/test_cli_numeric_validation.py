from contextlib import redirect_stderr
from io import StringIO
import unittest

from nasdaq_auto_trader.cli_parser import build_parser


class CliNumericValidationTests(unittest.TestCase):
    def test_parser_rejects_invalid_cash_interval_and_run_count(self):
        cases = [
            ["backtest", "--csv", "bars.csv", "--cash", "nan"],
            ["backtest", "--csv", "bars.csv", "--cash", "0"],
            ["loop", "--interval-minutes", "inf"],
            ["loop", "--interval-minutes", "0"],
            ["loop", "--max-runs", "0"],
        ]

        for arguments in cases:
            with self.subTest(arguments=arguments), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):
                    build_parser().parse_args(arguments)


if __name__ == "__main__":
    unittest.main()
