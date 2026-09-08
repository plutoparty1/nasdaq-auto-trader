from contextlib import redirect_stderr
from io import StringIO
import unittest

from nasdaq_auto_trader.cli_parser import build_parser


class CliNumericValidationTests(unittest.TestCase):
    def test_parser_exposes_session_authorization_commands(self):
        authorize = build_parser().parse_args(
            [
                "authorize-live-session",
                "--max-attempts",
                "12",
                "--confirm",
                "I UNDERSTAND THIS WILL PLACE REAL ORDERS DURING ONE NASDAQ SESSION",
            ]
        )
        revoke = build_parser().parse_args(["revoke-live-session"])

        self.assertEqual(authorize.command, "authorize-live-session")
        self.assertEqual(authorize.max_attempts, 12)
        self.assertEqual(revoke.command, "revoke-live-session")

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
