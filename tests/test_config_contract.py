import json
import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.broker import AlpacaCredentials, KISCredentials
from nasdaq_auto_trader.config import (
    AppConfig,
    load_config,
    validate_trading_mode,
)
from nasdaq_auto_trader.config_errors import ConfigLoadError, TradingModeValidationError


class ConfigContractTests(unittest.TestCase):
    def test_app_config_is_slotted_and_masks_credentials(self):
        config = AppConfig(
            alpaca=AlpacaCredentials("alpaca-key", "alpaca-secret", True),
            kis=KISCredentials("kis-key", "kis-secret", "12345678"),
        )

        payload = config.to_dict()

        self.assertFalse(hasattr(config, "__dict__"))
        self.assertEqual(payload["alpaca"]["api_key"], "***")
        self.assertEqual(payload["alpaca"]["secret_key"], "***")
        self.assertEqual(payload["kis"]["app_key"], "***")
        self.assertEqual(payload["kis"]["app_secret"], "***")
        self.assertEqual(payload["kis"]["account_no"], "***")

    def test_trading_mode_validation_raises_typed_value_error(self):
        config = AppConfig(mode="paper", broker="alpaca")

        with self.assertRaisesRegex(
            TradingModeValidationError,
            "paper/live mode requires ALPACA_API_KEY",
        ):
            validate_trading_mode(config)

    def test_load_config_rejects_non_object_nested_sections(self):
        malformed_sections = {
            "alpaca": "not-object",
            "kis": [],
            "strategy": "not-object",
            "risk": 42,
            "trading_agents": False,
        }

        for section, value in malformed_sections.items():
            with self.subTest(section=section), tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "config.json"
                path.write_text(json.dumps({section: value}), encoding="utf-8")

                with self.assertRaisesRegex(
                    ConfigLoadError,
                    f"{section} section must be an object",
                ):
                    load_config(path, environ={})


if __name__ == "__main__":
    unittest.main()
