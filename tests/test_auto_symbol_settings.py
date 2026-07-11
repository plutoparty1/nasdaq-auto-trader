import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import (
    TradingSettings,
    apply_settings_to_app_config,
    load_or_create_settings,
    save_settings,
    validate_settings,
)
from nasdaq_auto_trader.quant_data.resources import application_data_root


class AutoSymbolSettingsTests(unittest.TestCase):
    def test_auto_selection_setting_defaults_false_and_round_trips(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trading_config.json"
            original = TradingSettings(auto_symbol_selection_enabled=True)

            save_settings(original, path)
            loaded = load_or_create_settings(path)

        self.assertTrue(loaded.auto_symbol_selection_enabled)
        self.assertFalse(TradingSettings().auto_symbol_selection_enabled)

    def test_auto_mode_accepts_empty_ticker_and_does_not_use_ai_candidates(self):
        settings = TradingSettings(
            auto_symbol_selection_enabled=True,
            ticker="",
            ai_ticker_selection_enabled=True,
            ai_candidate_tickers=["TSLA"],
        )

        result = validate_settings(settings)
        config = apply_settings_to_app_config(AppConfig(), settings)

        self.assertTrue(result.ok)
        self.assertEqual(config.symbols, [])

    def test_manual_mode_still_requires_ticker(self):
        result = validate_settings(TradingSettings(ticker=""))

        self.assertFalse(result.ok)
        self.assertIn("ticker must not be empty", result.errors)

    def test_application_data_root_uses_external_local_app_data(self):
        root = application_data_root(
            environ={"LOCALAPPDATA": "C:/Users/test/AppData/Local"}
        )

        self.assertEqual(root.as_posix(), "C:/Users/test/AppData/Local/NasdaqAutoTrader")


if __name__ == "__main__":
    unittest.main()
