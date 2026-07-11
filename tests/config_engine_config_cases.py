from __future__ import annotations

from tests.config_engine_fixtures import *


class ConfigEngineConfigTests(unittest.TestCase):
    def test_live_mode_requires_explicit_allow_flag(self):
        config = AppConfig(
            mode="live",
            allow_live_trading=False,
            alpaca=AlpacaCredentials("key", "secret", paper=False),
        )

        with self.assertRaises(ValueError):
            validate_trading_mode(config)

    def test_live_mode_with_string_allow_flag_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "live",
                        "allow_live_trading": "false",
                        "alpaca": {
                            "api_key": "key",
                            "secret_key": "secret",
                            "paper": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, environ={})

        self.assertIs(config.allow_live_trading, False)
        with self.assertRaisesRegex(
            ValueError,
            "live trading requires allow_live_trading=true",
        ):
            validate_trading_mode(config)

    def test_string_false_broker_paper_flags_fail_closed_to_mode_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "live",
                        "broker": "kis",
                        "alpaca": {"paper": "false"},
                        "kis": {"paper": "false"},
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, environ={})

        self.assertIs(config.alpaca.paper, False)
        self.assertIs(config.kis.paper, False)

    def test_nested_string_false_booleans_fail_closed_to_dataclass_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "dry_run",
                        "strategy": {
                            "buy_trigger_enabled": "false",
                            "use_regime_filter": "false",
                        },
                        "risk": {"allow_additional_buy": "false"},
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, environ={})

        self.assertIs(config.strategy.buy_trigger_enabled, False)
        self.assertIs(config.strategy.use_regime_filter, True)
        self.assertIs(config.risk.allow_additional_buy, True)

    def test_real_nested_booleans_are_accepted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "dry_run",
                        "strategy": {
                            "buy_trigger_enabled": True,
                            "use_regime_filter": False,
                        },
                        "risk": {"allow_additional_buy": False},
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, environ={})

        self.assertIs(config.strategy.buy_trigger_enabled, True)
        self.assertIs(config.strategy.use_regime_filter, False)
        self.assertIs(config.risk.allow_additional_buy, False)

    def test_kis_live_mode_requires_credentials(self):
        config = AppConfig(
            mode="live",
            broker="kis",
            allow_live_trading=True,
        )

        with self.assertRaises(ValueError):
            validate_trading_mode(config)

    def test_load_config_reads_and_masks_kis_credentials(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "paper",
                        "broker": "kis",
                        "kis": {
                            "account_product_code": "01",
                            "order_exchange_code": "NASD",
                            "price_exchange_code": "NAS",
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(
                config_path,
                environ={
                    "KIS_APP_KEY": "app",
                    "KIS_APP_SECRET": "secret",
                    "KIS_ACCOUNT_NO": "12345678",
                },
            )

        self.assertEqual(config.broker, "kis")
        self.assertEqual(config.kis.app_key, "app")
        self.assertEqual(config.kis.account_no, "12345678")
        self.assertEqual(config.to_dict()["kis"]["app_key"], "***")
        self.assertEqual(config.to_dict()["kis"]["account_no"], "***")

    def test_load_config_reads_dotenv_next_to_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "paper",
                        "broker": "kis",
                    }
                ),
                encoding="utf-8",
            )
            (temp_path / ".env").write_text(
                "\n".join(
                    [
                        "KIS_APP_KEY=dotenv-app",
                        'KIS_APP_SECRET="dotenv-secret"',
                        "KIS_ACCOUNT_NO=87654321",
                        "KIS_ACCOUNT_PRODUCT_CODE=01",
                        "KIS_ORDER_EXCHANGE_CODE=NYSE",
                        "KIS_PRICE_EXCHANGE_CODE=NYS",
                        "KIS_CURRENCY=USD",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, environ={})

        self.assertEqual(config.kis.app_key, "dotenv-app")
        self.assertEqual(config.kis.app_secret, "dotenv-secret")
        self.assertEqual(config.kis.account_no, "87654321")
        self.assertEqual(config.kis.order_exchange_code, "NYSE")
        self.assertEqual(config.kis.price_exchange_code, "NYS")

    def test_environment_variables_override_dotenv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "paper",
                        "broker": "kis",
                    }
                ),
                encoding="utf-8",
            )
            (temp_path / ".env").write_text(
                "\n".join(
                    [
                        "KIS_APP_KEY=dotenv-app",
                        "KIS_APP_SECRET=dotenv-secret",
                        "KIS_ACCOUNT_NO=87654321",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_config(
                config_path,
                environ={
                    "KIS_APP_KEY": "real-env-app",
                    "KIS_APP_SECRET": "real-env-secret",
                    "KIS_ACCOUNT_NO": "12345678",
                },
            )

        self.assertEqual(config.kis.app_key, "real-env-app")
        self.assertEqual(config.kis.app_secret, "real-env-secret")
        self.assertEqual(config.kis.account_no, "12345678")
