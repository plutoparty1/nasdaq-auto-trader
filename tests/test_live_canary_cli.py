from __future__ import annotations

import unittest
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from contextlib import redirect_stderr, redirect_stdout
from nasdaq_auto_trader.__main__ import main as module_main

from nasdaq_auto_trader.cli_parser import build_parser
from nasdaq_auto_trader.cli_live_canary import run_canary_preflight
from nasdaq_auto_trader.live_canary_preflight import PreflightResult


class LiveCanaryCliParserTests(unittest.TestCase):
    def test_preflight_invalid_broker_returns_safe_json_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps({"mode": "dry_run", "broker": "alpaca"}),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "nasdaq_auto_trader",
                        "--config",
                        str(config_path),
                        "live-canary-preflight",
                    ],
                ),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = module_main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(payload["ready"])
        self.assertEqual(payload["submitted_order"], False)
        self.assertIn("broker=kis", payload["blockers"][0])
        self.assertNotIn("Traceback", stderr.getvalue())
    def test_preflight_command_has_no_order_enabling_switch(self):
        args = build_parser().parse_args(["live-canary-preflight"])

        self.assertEqual(args.command, "live-canary-preflight")
        self.assertNotIn("live_trading", vars(args))
        self.assertNotIn("confirm_live_orders", vars(args))

    def test_arm_requires_market_date_and_exact_confirmation_value(self):
        args = build_parser().parse_args(
            [
                "live-canary-arm",
                "--market-date",
                "2026-07-17",
                "--confirm",
                "I UNDERSTAND THIS WILL PLACE REAL ORDERS TODAY",
            ]
        )

        self.assertEqual(args.market_date, "2026-07-17")
        self.assertEqual(
            args.confirm,
            "I UNDERSTAND THIS WILL PLACE REAL ORDERS TODAY",
        )

    def test_service_has_only_bounded_test_loop_override(self):
        args = build_parser().parse_args(["live-canary", "--max-loops", "1"])

        self.assertEqual(args.max_loops, 1)

    def test_preflight_transport_explains_oauth_token_post_without_orders(self):
        result = PreflightResult(True, True, 0, 0, ())

        with patch("nasdaq_auto_trader.cli_live_canary._real_read_client"), patch(
            "nasdaq_auto_trader.cli_live_canary.run_preflight", return_value=result
        ):
            report = run_canary_preflight(object())

        self.assertEqual(
            report["transport"],
            "trading API GET-only (OAuth token acquisition may POST)",
        )
        self.assertFalse(report["submitted_order"])

    def test_arm_binds_source_mode_to_runtime_identity_path(self):
        expected_identity = Path("source-runtime")
        arm_result = type(
            "ArmResult",
            (),
            {"arm_path": Path("arm.json"), "state_path": Path("state.json")},
        )()

        with patch(
            "nasdaq_auto_trader.cli_live_canary.runtime_identity_path",
            return_value=expected_identity,
        ), patch("nasdaq_auto_trader.cli_live_canary._real_read_client"), patch(
            "nasdaq_auto_trader.cli_live_canary.issue_arm", return_value=arm_result
        ) as issue_arm:
            from nasdaq_auto_trader.cli_live_canary import run_canary_arm

            run_canary_arm(object(), "2026-07-17", "confirmation")

        request = issue_arm.call_args.args[0]
        self.assertEqual(request.executable, expected_identity)


if __name__ == "__main__":
    unittest.main()
