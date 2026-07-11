import json
import tempfile
import unittest
from pathlib import Path

from tests.ai_quant_fixtures import bars, promoted_payload, valid_spec_payload
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.models import AccountSnapshot, Bar, OrderRequest, Position


class FakeLegacyBroker:
    def __init__(self) -> None:
        self.orders: list[OrderRequest] = []

    def submit_order(self, order: OrderRequest) -> JsonObject:
        self.orders.append(order)
        return {"id": "broker-order-1", "status": "accepted"}


class FakeLegacyMarketData:
    def __init__(self) -> None:
        self.broker = FakeLegacyBroker()

    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        del timeframe, start, end, limit
        return {
            symbol: [
                Bar(
                    item.symbol,
                    item.timestamp,
                    item.open,
                    item.high,
                    item.low,
                    item.close,
                    item.volume,
                )
                for item in bars(symbol)
            ]
            for symbol in symbols
        }

    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(cash=100_000, equity=100_000, buying_power=100_000)

    def list_positions(self) -> dict[str, Position]:
        return {}

    def get_best_quote(self, symbol: str) -> JsonObject:
        del symbol
        return {"bid": 178.99, "ask": 179.01}


class FakeLegacyEngine:
    def __init__(self, market_data: FakeLegacyMarketData) -> None:
        self.market_data = market_data
        self.broker = market_data.broker


class AIQuantLiveIntegrationTests(unittest.TestCase):
    def test_disabled_quant_live_cycle_blocks_before_existing_engine_is_created(self):
        from nasdaq_auto_trader.execution.live_integration import (
            AIQuantRuntimePaths,
            run_ai_quant_live_cycle,
        )

        def fail_if_created(config: AppConfig) -> FakeLegacyEngine:
            del config
            raise AssertionError("existing engine should not be created")

        result = run_ai_quant_live_cycle(
            AppConfig(),
            AIQuantRuntimePaths(),
            engine_factory=fail_if_created,
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.blocked_reasons, ("live_trading_disabled",))

    def test_enabled_quant_live_cycle_routes_order_through_existing_broker_adapter(self):
        from nasdaq_auto_trader.execution.live_integration import (
            AIQuantRuntimePaths,
            run_ai_quant_live_cycle,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            config_path = base / "ai_quant_config.json"
            registry_path = base / "registry.json"
            promoted_path = base / "promoted_strategy.json"
            spec_dir = base / "specs"
            spec_dir.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "ai_quant_lab_enabled": True,
                        "live_trading": True,
                        "dry_run": False,
                        "controlled_live_enabled": True,
                        "max_order_notional": 1_000,
                    }
                ),
                encoding="utf-8",
            )
            promoted_path.write_text(
                json.dumps(promoted_payload("auto_generated_strategy_001")),
                encoding="utf-8",
            )
            (spec_dir / "auto_generated_strategy_001-v1.json").write_text(
                json.dumps(valid_spec_payload()),
                encoding="utf-8",
            )
            market_data = FakeLegacyMarketData()
            app_config = AppConfig(
                mode="live",
                allow_live_trading=True,
                alpaca=AlpacaCredentials("key", "secret", paper=False),
            )

            result = run_ai_quant_live_cycle(
                app_config,
                AIQuantRuntimePaths(
                    ai_config_path=config_path,
                    registry_path=registry_path,
                    promoted_path=promoted_path,
                    spec_dir=spec_dir,
                    audit_log_path=base / "audit.jsonl",
                ),
                engine_factory=lambda config: FakeLegacyEngine(market_data),
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.submitted_orders, 1)
        self.assertEqual(len(market_data.broker.orders), 1)
        self.assertIsInstance(market_data.broker.orders[0], OrderRequest)
        self.assertEqual(market_data.broker.orders[0].symbol, "QQQ")

    def test_live_cycle_submits_zero_orders_when_risk_guard_blocks_order(self):
        from nasdaq_auto_trader.execution.live_integration import (
            AIQuantRuntimePaths,
            run_ai_quant_live_cycle,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            config_path = base / "ai_quant_config.json"
            registry_path = base / "registry.json"
            promoted_path = base / "promoted_strategy.json"
            spec_dir = base / "specs"
            spec_dir.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "ai_quant_lab_enabled": True,
                        "live_trading": True,
                        "dry_run": False,
                        "controlled_live_enabled": True,
                        "max_order_notional": 1,
                    }
                ),
                encoding="utf-8",
            )
            promoted_path.write_text(
                json.dumps(promoted_payload("auto_generated_strategy_001")),
                encoding="utf-8",
            )
            (spec_dir / "auto_generated_strategy_001-v1.json").write_text(
                json.dumps(valid_spec_payload()),
                encoding="utf-8",
            )
            market_data = FakeLegacyMarketData()
            app_config = AppConfig(
                mode="live",
                allow_live_trading=True,
                alpaca=AlpacaCredentials("key", "secret", paper=False),
            )

            result = run_ai_quant_live_cycle(
                app_config,
                AIQuantRuntimePaths(
                    ai_config_path=config_path,
                    registry_path=registry_path,
                    promoted_path=promoted_path,
                    spec_dir=spec_dir,
                    audit_log_path=base / "audit.jsonl",
                ),
                engine_factory=lambda config: FakeLegacyEngine(market_data),
            )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.submitted_orders, 0)
        self.assertEqual(result.blocked_reasons, ("order_qty_below_minimum",))
        self.assertEqual(market_data.broker.orders, [])

    def test_market_health_fails_closed_without_quote_when_spread_filter_enabled(self):
        from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
        from nasdaq_auto_trader.execution.live_integration import (
            ExistingEngineMarketDataAdapter,
        )

        class NoQuoteMarketData:
            def get_stock_bars(
                self,
                symbols: list[str],
                timeframe: str,
                start: str,
                end: str | None = None,
                limit: int = 1000,
            ) -> dict[str, list[Bar]]:
                del timeframe, start, end, limit
                return {symbol: [] for symbol in symbols}

            def get_account(self) -> AccountSnapshot:
                return AccountSnapshot(cash=1, equity=1, buying_power=1)

            def list_positions(self) -> dict[str, Position]:
                return {}

        health = ExistingEngineMarketDataAdapter(
            AppConfig(),
            NoQuoteMarketData(),
            AIQuantConfig(spread_filter_enabled=True),
        ).market_health("QQQ")

        self.assertFalse(health.price_available)
        self.assertTrue(health.spread_abnormal)


if __name__ == "__main__":
    unittest.main()
