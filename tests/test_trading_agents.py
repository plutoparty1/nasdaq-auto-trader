import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


from nasdaq_auto_trader.broker import AlpacaCredentials
from nasdaq_auto_trader.cli import main
from nasdaq_auto_trader.config import AppConfig, load_config
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, Bar, TradeDecision
from nasdaq_auto_trader.risk import RiskConfig
from nasdaq_auto_trader.strategy import StrategyConfig
from nasdaq_auto_trader.trading_agents import (
    TradingAgentsAdvisor,
    TradingAgentsConfig,
    apply_trading_agents_policy,
)


def compact_strategy_config(**overrides):
    defaults = {
        "sma_fast": 5,
        "sma_slow": 20,
        "ema_fast": 6,
        "ema_slow": 13,
        "rsi_period": 14,
        "macd_fast": 6,
        "macd_slow": 13,
        "macd_signal": 5,
        "bollinger_period": 20,
        "long_sma": 30,
        "momentum_period": 10,
        "donchian_period": 20,
        "stochastic_period": 14,
        "volume_period": 20,
        "atr_period": 14,
        "buy_score": 5,
        "sell_score": 4,
    }
    defaults.update(overrides)
    return StrategyConfig(**defaults)


class FakeBroker:
    def __init__(self):
        self.orders = []

    def submit_order(self, order):
        self.orders.append(order)
        return {"status": "fake_submitted"}


class BuySignalMarketData:
    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        bars = []
        for index in range(70):
            close = 100 + index
            bars.append(
                Bar(
                    symbol=symbols[0],
                    timestamp=f"T{index + 1:03d}",
                    open=close - 0.5,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=1_000_000 + index,
                )
            )
        return {symbols[0]: bars}


class FakeTradingAgentsGraph:
    calls = []

    def __init__(self, selected_analysts, debug, config):
        self.selected_analysts = selected_analysts
        self.debug = debug
        self.config = config

    def propagate(self, symbol, analysis_date, asset_type="stock"):
        self.calls.append((symbol, analysis_date, asset_type, self.selected_analysts))
        return {"final_trade_decision": "**Rating**: Overweight"}, "**Rating**: Overweight"


class FakeHoldAdvisor:
    def analyze(self, symbol, analysis_date, asset_type=None):
        return {
            "status": "ok",
            "symbol": symbol,
            "analysis_date": analysis_date,
            "normalized_action": "hold",
            "submitted_order": False,
        }


class TradingAgentsIntegrationTests(unittest.TestCase):
    def test_advisor_runs_injected_graph_and_never_submits_order(self):
        config = TradingAgentsConfig(
            enabled=True,
            selected_analysts=["market", "news"],
            llm_provider="openai",
            deep_think_llm="deep-model",
            quick_think_llm="quick-model",
            output_language="Korean",
        )
        advisor = TradingAgentsAdvisor(
            config,
            graph_cls=FakeTradingAgentsGraph,
            default_config={
                "llm_provider": "openai",
                "deep_think_llm": "default-deep",
                "quick_think_llm": "default-quick",
            },
        )

        result = advisor.analyze("NVDA", "2026-01-15")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["normalized_action"], "buy")
        self.assertEqual(result["submitted_order"], False)
        self.assertEqual(result["selected_analysts"], ["market", "news"])
        self.assertEqual(FakeTradingAgentsGraph.calls[-1][0], "NVDA")

    def test_confirm_policy_blocks_order_when_tradingagents_disagrees(self):
        decision = TradeDecision("QQQ", "buy", 10, 100, ["technical_buy"], 5)
        config = TradingAgentsConfig(enabled=True, decision_policy="confirm")

        adjusted = apply_trading_agents_policy(
            decision,
            {"status": "ok", "normalized_action": "hold"},
            config,
        )

        self.assertEqual(adjusted.action, "hold")
        self.assertIn("tradingagents_hold_did_not_confirm_buy", adjusted.reasons)

    def test_engine_confirm_policy_prevents_unconfirmed_buy_order(self):
        config = AppConfig(
            mode="dry_run",
            symbols=["QQQ"],
            strategy=compact_strategy_config(),
            risk=RiskConfig(max_position_pct=0.2, risk_per_trade_pct=0),
            trading_agents=TradingAgentsConfig(
                enabled=True,
                decision_policy="confirm",
                analysis_date="2026-01-15",
            ),
        )
        broker = FakeBroker()
        engine = TradingEngine(
            config,
            broker=broker,
            market_data=BuySignalMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
            clock=lambda: datetime(2026, 1, 15, tzinfo=timezone.utc),
        )
        engine.trading_agents = FakeHoldAdvisor()

        result = engine.run_once()[0]

        self.assertEqual(result["decision"].action, "hold")
        self.assertIsNone(result["order"])
        self.assertEqual(broker.orders, [])
        self.assertEqual(result["trading_agents"]["normalized_action"], "hold")

    def test_config_loads_trading_agents_block(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "dry_run",
                        "trading_agents": {
                            "enabled": True,
                            "decision_policy": "confirm",
                            "selected_analysts": ["market"],
                            "analysis_date": "2026-01-15",
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, environ={})

        self.assertTrue(config.trading_agents.enabled)
        self.assertEqual(config.trading_agents.decision_policy, "confirm")
        self.assertEqual(config.trading_agents.selected_analysts, ["market"])

    def test_config_string_false_does_not_enable_trading_agents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "dry_run",
                        "trading_agents": {
                            "enabled": "false",
                            "fail_closed": "false",
                            "checkpoint_enabled": "false",
                            "debug": "false",
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, environ={})

        self.assertIs(config.trading_agents.enabled, False)
        self.assertIs(config.trading_agents.fail_closed, True)
        self.assertIs(config.trading_agents.checkpoint_enabled, False)
        self.assertIs(config.trading_agents.debug, False)

    def test_config_real_booleans_enable_trading_agents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "dry_run",
                        "trading_agents": {
                            "enabled": True,
                            "fail_closed": False,
                            "checkpoint_enabled": True,
                            "debug": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, environ={})

        self.assertIs(config.trading_agents.enabled, True)
        self.assertIs(config.trading_agents.fail_closed, False)
        self.assertIs(config.trading_agents.checkpoint_enabled, True)
        self.assertIs(config.trading_agents.debug, True)

    def test_cli_trading_agents_unavailable_is_no_order_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "mode": "dry_run",
                        "broker": "alpaca",
                        "symbols": ["NVDA"],
                        "alpaca": {"paper": True},
                    }
                ),
                encoding="utf-8",
            )

            output = io.StringIO()
            with patch(
                "nasdaq_auto_trader.trading_agents.importlib.import_module",
                side_effect=ModuleNotFoundError("tradingagents"),
            ):
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "--config",
                            str(config_path),
                            "trading-agents",
                            "--symbol",
                            "NVDA",
                            "--date",
                            "2026-01-15",
                        ]
                    )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["submitted_order"], False)
        self.assertEqual(payload["dry_run"], True)


if __name__ == "__main__":
    unittest.main()
