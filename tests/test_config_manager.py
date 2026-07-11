import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import (
    SettingsLoadError,
    TradingSessionState,
    TradingSettings,
    apply_settings_to_app_config,
    load_or_create_settings,
    save_settings,
    settings_from_dict,
    validate_order_against_settings,
    validate_settings,
)
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest, Position


class ConfigManagerTests(unittest.TestCase):
    def test_missing_settings_file_is_created_with_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trading_config.json"

            settings = load_or_create_settings(path)
            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(settings.ticker, "QQQ")
        self.assertTrue(settings.dry_run)
        self.assertFalse(settings.live_trading)
        self.assertEqual(saved["order_qty"], 1)
        self.assertFalse(settings.ai_ticker_selection_enabled)
        self.assertTrue(settings.ai_recommend_only)
        self.assertEqual(settings.ai_candidate_tickers, ["AAPL", "MSFT", "NVDA", "TSLA", "QQQ"])

    def test_settings_round_trip_and_blank_values_use_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trading_config.json"
            settings = TradingSettings(
                ticker="NVDA",
                order_qty=3,
                max_position_qty=3,
                dry_run=False,
            )

            save_settings(settings, path)
            loaded = load_or_create_settings(path)
            defaulted = settings_from_dict({"ticker": "", "order_qty": ""})

        self.assertEqual(loaded.ticker, "NVDA")
        self.assertEqual(loaded.order_qty, 3)
        self.assertEqual(defaulted.ticker, "QQQ")
        self.assertEqual(defaulted.order_qty, 1)

    def test_ai_settings_parse_and_validate_candidate_list(self):
        settings = settings_from_dict(
            {
                "ai_ticker_selection_enabled": True,
                "ai_candidate_tickers": "nvda, tsla, qqq",
                "ai_min_confidence": "0.8",
                "ai_max_order_qty": "1",
            }
        )
        invalid = TradingSettings(
            ai_ticker_selection_enabled=True,
            ai_candidate_tickers=[],
        )
        invalid_action = TradingSettings(ai_fail_action="place_order")

        self.assertEqual(settings.ai_candidate_tickers, ["NVDA", "TSLA", "QQQ"])
        self.assertEqual(settings.ai_min_confidence, 0.8)
        self.assertFalse(validate_settings(invalid).ok)
        self.assertFalse(validate_settings(invalid_action).ok)

    def test_broken_json_blocks_settings_load(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trading_config.json"
            path.write_text("{broken", encoding="utf-8")

            with self.assertRaises(SettingsLoadError):
                load_or_create_settings(path)

    def test_validation_errors_and_live_warnings(self):
        invalid = TradingSettings(ticker="", order_qty=0, max_position_qty=0)
        live_warning = TradingSettings(
            live_trading=True,
            dry_run=True,
            require_confirm_before_buy=False,
            require_confirm_before_sell=False,
        )

        invalid_result = validate_settings(invalid)
        warning_result = validate_settings(live_warning)

        self.assertFalse(invalid_result.ok)
        self.assertIn("ticker must not be empty", invalid_result.errors)
        self.assertTrue(warning_result.ok)
        self.assertEqual(len(warning_result.warnings), 2)

    def test_legacy_ai_direct_order_warning_matches_fail_closed_contract(self):
        settings = TradingSettings(
            live_trading=True,
            dry_run=False,
            ai_trade_decision_enabled=True,
            ai_recommend_only=False,
            require_confirm_after_ai=False,
        )

        result = validate_settings(settings)

        self.assertIn(
            "legacy AI direct orders remain disabled: final order submission "
            "will block with ai_direct_order_disabled",
            result.warnings,
        )

    def test_settings_apply_to_existing_app_config(self):
        settings = TradingSettings(
            live_trading=False,
            dry_run=False,
            ticker="tsla",
            order_qty=2,
            max_position_qty=5,
            buy_rsi_threshold=25,
            sell_rsi_threshold=75,
            short_ma_period=7,
            long_ma_period=21,
            take_profit_rate=6,
            stop_loss_rate=2,
        )

        config = apply_settings_to_app_config(AppConfig(mode="dry_run"), settings)

        self.assertEqual(config.mode, "paper")
        self.assertEqual(config.symbols, ["TSLA"])
        self.assertEqual(config.strategy.rsi_oversold, 25)
        self.assertEqual(config.strategy.rsi_overbought, 75)
        self.assertEqual(config.strategy.sma_fast, 7)
        self.assertEqual(config.strategy.sma_slow, 21)
        self.assertEqual(config.strategy.take_profit_pct, 0.06)
        self.assertEqual(config.strategy.stop_loss_pct, 0.02)
        self.assertEqual(config.risk.order_qty, 2)
        self.assertEqual(config.risk.max_position_qty, 5)

    def test_ai_candidate_settings_become_config_symbols_when_ai_enabled(self):
        settings = TradingSettings(
            dry_run=True,
            ai_ticker_selection_enabled=True,
            ai_candidate_tickers=["nvda", "tsla"],
            ai_max_order_qty=1,
            max_position_qty=2,
        )

        config = apply_settings_to_app_config(AppConfig(mode="dry_run"), settings)

        self.assertEqual(config.symbols, ["NVDA", "TSLA"])

    def test_disabled_ai_order_quantity_does_not_block_unrelated_settings(self):
        disabled = TradingSettings(
            ai_order_qty_enabled=False,
            ai_max_order_qty=5,
            max_position_qty=1,
        )
        enabled = TradingSettings(
            ai_order_qty_enabled=True,
            ai_max_order_qty=5,
            max_position_qty=1,
        )

        disabled_result = validate_settings(disabled)
        enabled_result = validate_settings(enabled)

        self.assertTrue(disabled_result.ok)
        self.assertIn(
            "ai_max_order_qty must be less than or equal to max_position_qty",
            enabled_result.errors,
        )

    def test_order_runtime_guard_blocks_unsafe_buys(self):
        settings = TradingSettings(
            sell_only=False,
            allow_additional_buy=False,
            order_qty=1,
            max_position_qty=1,
            min_cash_to_buy=50,
            market_close_stop_minutes=10,
        )
        state = TradingSessionState(starting_equity=1000)
        order = OrderRequest(symbol="QQQ", side="buy", qty=1)
        account = AccountSnapshot(cash=100, equity=1000, buying_power=100)
        position = Position(symbol="QQQ", qty=1, market_value=100, avg_entry_price=100)

        response = validate_order_against_settings(
            order,
            account,
            position,
            settings,
            state,
            datetime(2026, 6, 30, 18, 0, tzinfo=timezone.utc),
            mode="dry_run",
        )

        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["reason"], "additional_buy_disabled")

    def test_order_runtime_guard_blocks_daily_loss_and_close_stop(self):
        settings = TradingSettings(max_daily_loss_rate=5, market_close_stop_minutes=10)
        order = OrderRequest(symbol="QQQ", side="buy", qty=1)
        state = TradingSessionState(starting_equity=1000)

        loss_response = validate_order_against_settings(
            order,
            AccountSnapshot(cash=100, equity=940, buying_power=100),
            None,
            settings,
            state,
            datetime(2026, 6, 30, 18, 0, tzinfo=timezone.utc),
            mode="dry_run",
        )

        close_response = validate_order_against_settings(
            order,
            AccountSnapshot(cash=100, equity=1000, buying_power=100),
            None,
            settings,
            TradingSessionState(starting_equity=1000),
            datetime(2026, 6, 30, 19, 55, tzinfo=timezone.utc),
            mode="dry_run",
        )

        self.assertEqual(loss_response["reason"], "max_daily_loss_reached")
        self.assertEqual(close_response["reason"], "market_close_stop_active")


if __name__ == "__main__":
    unittest.main()
