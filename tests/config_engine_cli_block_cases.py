from __future__ import annotations

from tests.config_engine_fixtures import *


class ConfigEngineCliBlockTests(unittest.TestCase):
    def test_cli_once_live_path_blocks_without_final_confirmation(self):
        broker = FakeBroker()
        original_engine = cli_module.TradingEngine

        def fake_engine(config, live_order_confirmation=False):
            return TradingEngine(
                config,
                broker=broker,
                market_data=FakeMarketData(),
                account=AccountSnapshot(
                    cash=10_000,
                    equity=10_000,
                    buying_power=10_000,
                ),
                positions={},
                live_order_confirmation=live_order_confirmation,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "live",
                        "allow_live_trading": True,
                        "regular_market_hours_only": False,
                        "alpaca": {
                            "api_key": "key",
                            "secret_key": "secret",
                            "paper": False,
                        },
                        "strategy": asdict(compact_strategy_config()),
                        "risk": {
                            "max_position_pct": 0.2,
                            "risk_per_trade_pct": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (Path(temp_dir) / ".env").write_text(
                "NASDAQ_AUTO_TRADER_ALLOW_LIVE=YES\n", encoding="utf-8"
            )
            output = io.StringIO()
            cli_module.TradingEngine = fake_engine
            try:
                with redirect_stdout(output):
                    exit_code = main(["--config", str(config_path), "once"])
            finally:
                cli_module.TradingEngine = original_engine

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload[0]["response"]["status"], "blocked")
        self.assertEqual(payload[0]["response"]["reason"], "live_order_confirmation_required")
        self.assertEqual(broker.orders, [])

    def test_cli_loop_live_path_blocks_without_final_confirmation(self):
        broker = FakeBroker()
        original_engine = cli_module.TradingEngine

        def fake_engine(config, live_order_confirmation=False):
            return TradingEngine(
                config,
                broker=broker,
                market_data=FakeMarketData(),
                account=AccountSnapshot(
                    cash=10_000,
                    equity=10_000,
                    buying_power=10_000,
                ),
                positions={},
                live_order_confirmation=live_order_confirmation,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "live",
                        "allow_live_trading": True,
                        "regular_market_hours_only": False,
                        "alpaca": {
                            "api_key": "key",
                            "secret_key": "secret",
                            "paper": False,
                        },
                        "strategy": asdict(compact_strategy_config()),
                        "risk": {
                            "max_position_pct": 0.2,
                            "risk_per_trade_pct": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (Path(temp_dir) / ".env").write_text(
                "NASDAQ_AUTO_TRADER_ALLOW_LIVE=YES\n", encoding="utf-8"
            )
            output = io.StringIO()
            cli_module.TradingEngine = fake_engine
            try:
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "--config",
                            str(config_path),
                            "loop",
                            "--interval-minutes",
                            "1",
                            "--max-runs",
                            "1",
                        ]
                    )
            finally:
                cli_module.TradingEngine = original_engine

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload[0]["response"]["status"], "blocked")
        self.assertEqual(payload[0]["response"]["reason"], "live_order_confirmation_required")
        self.assertEqual(broker.orders, [])
