import json
import tempfile
import unittest
from pathlib import Path

from tests.ai_quant_fixtures import valid_spec_payload
from nasdaq_auto_trader.ai_quant_lab.config import (
    live_order_block_reason,
    load_ai_quant_config,
)
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import (
    parse_strategy_spec_json,
    validate_strategy_spec,
)


class AIQuantParserBoundaryTests(unittest.TestCase):
    def test_config_parses_insane_search_command_array(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "insane_search_command": ["python", "runner.py"],
                        "insane_search_timeout_seconds": 7,
                    }
                ),
                encoding="utf-8",
            )

            config = load_ai_quant_config(config_path)

        self.assertEqual(config.insane_search_command, ("python", "runner.py"))
        self.assertEqual(config.insane_search_timeout_seconds, 7)

    def test_malformed_insane_search_command_loads_fail_closed_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                '{"live_trading": true, "dry_run": false, '
                '"controlled_live_enabled": true, '
                '"insane_search_command": "python runner.py"}',
                encoding="utf-8",
            )

            config = load_ai_quant_config(config_path)

        self.assertEqual(config.insane_search_command, ())
        self.assertEqual(live_order_block_reason(config), "live_trading_disabled")

    def test_malformed_known_config_field_loads_fail_closed_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                '{"live_trading": true, "dry_run": false, '
                '"controlled_live_enabled": true, "max_order_notional": "bad"}',
                encoding="utf-8",
            )

            config = load_ai_quant_config(config_path)

        self.assertEqual(live_order_block_reason(config), "live_trading_disabled")

    def test_overflow_config_number_loads_fail_closed_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                '{"live_trading": true, "dry_run": false, '
                '"controlled_live_enabled": true, "max_order_notional": 1e9999}',
                encoding="utf-8",
            )

            config = load_ai_quant_config(config_path)

        self.assertEqual(live_order_block_reason(config), "live_trading_disabled")

    def test_strategy_schema_rejects_bool_signal_parameter(self):
        payload = valid_spec_payload()
        payload["signals"][0]["lookback_days"] = True

        validation = validate_strategy_spec(payload)

        self.assertFalse(validation.valid)
        self.assertIn("signal_parameter_lookback_days_must_be_number", validation.reasons)

    def test_strategy_schema_rejects_overflow_signal_parameter_json(self):
        payload = valid_spec_payload()
        text = json.dumps(payload).replace('"lookback_days": 20', '"lookback_days": 1e9999', 1)

        validation = parse_strategy_spec_json(text)

        self.assertFalse(validation.valid)
        self.assertIn("strategy_spec_invalid_json", validation.reasons)

    def test_strategy_schema_rejects_unknown_deep_universe_filter(self):
        payload = valid_spec_payload()
        payload["universe"] = {"filters": {"unlisted_deep": True}}

        validation = validate_strategy_spec(payload)

        self.assertFalse(validation.valid)
        self.assertIn("unknown_field:universe.filters.unlisted_deep", validation.reasons)

    def test_strategy_schema_rejects_object_in_scalar_field(self):
        payload = valid_spec_payload()
        payload["research_basis"]["summary"] = {"nested": "not allowed"}

        validation = validate_strategy_spec(payload)

        self.assertFalse(validation.valid)
        self.assertIn("research_basis.summary_must_be_string", validation.reasons)


if __name__ == "__main__":
    unittest.main()
