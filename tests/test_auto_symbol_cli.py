import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import nasdaq_auto_trader.cli as cli_module
from nasdaq_auto_trader.cli import main
from nasdaq_auto_trader.cli_parser import build_parser
from nasdaq_auto_trader.quant_data.symbol_selector import (
    RankedSymbol,
    SelectionReport,
)


class AutoSymbolCliTests(unittest.TestCase):
    def test_parser_exposes_preview_and_auto_execution_flags(self):
        preview = build_parser().parse_args(
            ["select-symbols", "--trading-config", "settings.json"]
        )
        once = build_parser().parse_args(["once", "--auto-select"])
        loop = build_parser().parse_args(
            [
                "loop",
                "--auto-select",
                "--live-auth-minutes",
                "5",
                "--live-max-cycles",
                "2",
            ]
        )

        self.assertEqual(preview.command, "select-symbols")
        self.assertEqual(preview.trading_config, "settings.json")
        self.assertTrue(once.auto_select)
        self.assertEqual(loop.live_auth_minutes, 5)
        self.assertEqual(loop.live_max_cycles, 2)

    def test_auto_once_live_disabled_blocks_before_engine_construction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = _write_config(Path(temp_dir), allow_live=False)
            output = io.StringIO()
            with patch.object(
                cli_module,
                "TradingEngine",
                side_effect=AssertionError("engine must not be constructed"),
            ):
                with redirect_stdout(output):
                    exit_code = main(
                        ["--config", str(config_path), "once", "--auto-select"]
                    )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["reason"], "live_trading_disabled")

    def test_auto_once_live_confirmation_is_independent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = _write_config(Path(temp_dir), allow_live=True)
            output = io.StringIO()
            with patch.object(
                cli_module,
                "TradingEngine",
                side_effect=AssertionError("engine must not be constructed"),
            ):
                with redirect_stdout(output):
                    exit_code = main(
                        ["--config", str(config_path), "once", "--auto-select"]
                    )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["reason"], "live_order_confirmation_required")

    def test_auto_loop_requires_bounded_live_authorization(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = _write_config(Path(temp_dir), allow_live=True)
            output = io.StringIO()
            with patch.object(
                cli_module,
                "TradingEngine",
                side_effect=AssertionError("engine must not be constructed"),
            ):
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "--config",
                            str(config_path),
                            "loop",
                            "--auto-select",
                            "--confirm-live-orders",
                        ]
                    )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["reason"], "live_authorization_required")

    def test_auto_loop_reuses_one_engine(self):
        engines = []

        class FakeEngine:
            def __init__(self, *args, **kwargs):
                del args, kwargs
                engines.append(self)
                self.last_selection_report = _selection_report()

            def run_once(self):
                return []

        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "trading.json"
            output = io.StringIO()
            with patch.object(cli_module, "TradingEngine", FakeEngine):
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "loop",
                            "--mode",
                            "dry_run",
                            "--auto-select",
                            "--trading-config",
                            str(settings_path),
                            "--interval-minutes",
                            "0.0001",
                            "--max-runs",
                            "2",
                        ]
                    )

        payloads = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(engines), 1)
        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[0]["selection"]["strategy_id"], "learned")

    def test_select_symbols_exit_contract_never_constructs_engine(self):
        selected_output = io.StringIO()
        with patch(
            "nasdaq_auto_trader.cli_main._run_select_symbols",
            return_value=_selection_report(),
        ):
            with patch.object(
                cli_module,
                "TradingEngine",
                side_effect=AssertionError("preview must not construct engine"),
            ):
                with redirect_stdout(selected_output):
                    selected_exit = main(["select-symbols"])

        blocked_output = io.StringIO()
        blocked = replace(
            _selection_report(),
            status="blocked",
            selected_symbols=(),
            blocked_reasons=("eligible_strategy_unavailable",),
        )
        with patch(
            "nasdaq_auto_trader.cli_main._run_select_symbols",
            return_value=blocked,
        ):
            with redirect_stdout(blocked_output):
                blocked_exit = main(["select-symbols"])

        self.assertEqual(selected_exit, 0)
        self.assertEqual(blocked_exit, 2)
        self.assertFalse(json.loads(selected_output.getvalue())["submitted_order"])
        self.assertEqual(
            json.loads(blocked_output.getvalue())["blocked_reasons"],
            ["eligible_strategy_unavailable"],
        )

    def test_auto_live_loop_stops_at_cycle_authorization_limit(self):
        engines = []

        class FakeEngine:
            def __init__(self, *args, **kwargs):
                del args, kwargs
                engines.append(self)
                self.last_selection_report = _selection_report()

            def run_once(self):
                return []

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = _write_config(Path(temp_dir), allow_live=True)
            settings_path = Path(temp_dir) / "trading.json"
            output = io.StringIO()
            with patch.object(cli_module, "TradingEngine", FakeEngine):
                with patch("nasdaq_auto_trader.cli_commands_basic.time.sleep"):
                    with redirect_stdout(output):
                        exit_code = main(
                            [
                                "--config",
                                str(config_path),
                                "loop",
                                "--auto-select",
                                "--trading-config",
                                str(settings_path),
                                "--confirm-live-orders",
                                "--live-auth-minutes",
                                "5",
                                "--live-max-cycles",
                                "1",
                                "--interval-minutes",
                                "1",
                            ]
                        )

        payloads = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(exit_code, 2)
        self.assertEqual(len(engines), 1)
        self.assertEqual(len(payloads), 2)
        self.assertEqual(
            payloads[-1]["reason"],
            "live_authorization_cycle_limit_reached",
        )

    def test_selection_output_excludes_sensitive_portfolio_fields(self):
        from nasdaq_auto_trader.cli_formatters import selection_report_to_dict

        payload = selection_report_to_dict(_selection_report())
        serialized = json.dumps(payload)

        for forbidden in (
            "cash",
            "buying_power",
            "account_no",
            "secret_key",
            "api_key",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(payload["ranked"][0]["reasons"], ["momentum"])


def _selection_report() -> SelectionReport:
    return SelectionReport(
        status="selected",
        universe_id="nasdaq-100",
        universe_effective_date="2026-07-10",
        strategy_id="learned",
        strategy_version="v1",
        strategy_digest="digest",
        shortlist_count=1,
        ranked=(RankedSymbol("QQQ", 1.5, 0.8, ("momentum",)),),
        selected_symbols=("QQQ",),
    )


def _write_config(root: Path, allow_live: bool) -> Path:
    path = root / "config.json"
    path.write_text(
        json.dumps(
            {
                "mode": "live",
                "allow_live_trading": allow_live,
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
    if allow_live:
        (root / ".env").write_text(
            "NASDAQ_AUTO_TRADER_ALLOW_LIVE=YES\n",
            encoding="utf-8",
        )
    return path


if __name__ == "__main__":
    unittest.main()
