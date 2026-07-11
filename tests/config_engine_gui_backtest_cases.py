from __future__ import annotations

from tests.config_engine_fixtures import *


class ConfigEngineGuiBacktestTests(unittest.TestCase):
    def test_gui_settings_confirmation_blocks_pre_submit_order(self):
        settings = TradingSettings(
            dry_run=False,
            live_trading=False,
            require_confirm_before_buy=True,
            ticker="QQQ",
            order_qty=1,
            max_position_qty=1,
        )
        config = apply_settings_to_app_config(
            AppConfig(
                mode="dry_run",
                alpaca=AlpacaCredentials("key", "secret"),
                strategy=compact_strategy_config(),
            ),
            settings,
        )
        broker = FakeBroker()
        engine = TradingEngine(
            config,
            broker=broker,
            market_data=FakeMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
            clock=lambda: datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
            trading_settings=settings,
            trading_session_state=TradingSessionState(),
        )

        result = engine.run_once()[0]

        self.assertEqual(result["decision"].action, "buy")
        self.assertEqual(result["order"].side, "buy")
        self.assertEqual(result["response"]["status"], "blocked")
        self.assertEqual(result["response"]["reason"], "buy_confirmation_required")
        self.assertEqual(broker.orders, [])

    def test_gui_settings_sell_only_blocks_buy_order(self):
        settings = TradingSettings(
            dry_run=True,
            sell_only=True,
            require_confirm_before_buy=False,
            ticker="QQQ",
            order_qty=1,
            max_position_qty=1,
        )
        config = apply_settings_to_app_config(
            AppConfig(mode="dry_run", strategy=compact_strategy_config()),
            settings,
        )
        broker = FakeBroker()
        engine = TradingEngine(
            config,
            broker=broker,
            market_data=FakeMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={},
            trading_settings=settings,
            trading_session_state=TradingSessionState(),
        )

        result = engine.run_once()[0]

        self.assertEqual(result["decision"].action, "buy")
        self.assertEqual(result["response"]["reason"], "sell_only_mode")
        self.assertEqual(broker.orders, [])

    def test_gui_settings_time_based_sell_turns_hold_into_sell(self):
        now = datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc)
        settings = TradingSettings(
            dry_run=True,
            require_confirm_before_sell=False,
            time_based_sell_enabled=True,
            max_holding_minutes=1,
            take_profit_rate=500,
            stop_loss_rate=100,
            order_qty=1,
            max_position_qty=2,
        )
        config = apply_settings_to_app_config(
            AppConfig(mode="dry_run", strategy=compact_strategy_config(sell_score=999)),
            settings,
        )
        broker = FakeBroker()
        session_state = TradingSessionState()
        session_state.position_first_seen_at["QQQ"] = now - timedelta(minutes=2)
        engine = TradingEngine(
            config,
            broker=broker,
            market_data=FakeMarketData(),
            account=AccountSnapshot(cash=10_000, equity=10_000, buying_power=10_000),
            positions={
                "QQQ": Position(
                    symbol="QQQ",
                    qty=2,
                    market_value=338,
                    avg_entry_price=169,
                )
            },
            clock=lambda: now,
            trading_settings=settings,
            trading_session_state=session_state,
        )

        result = engine.run_once()[0]

        self.assertEqual(result["decision"].action, "sell")
        self.assertIn("max_holding_minutes", result["decision"].reasons)
        self.assertEqual(result["order"].side, "sell")
        self.assertEqual(result["order"].qty, 1)

    def test_market_session_blocks_holiday_and_early_close_after_1pm(self):
        christmas = regular_market_session(
            datetime(2026, 12, 25, 15, 0, tzinfo=timezone.utc)
        )
        day_after_thanksgiving = regular_market_session(
            datetime(2026, 11, 27, 19, 0, tzinfo=timezone.utc)
        )

        self.assertFalse(christmas.is_open)
        self.assertEqual(christmas.reason, "market_holiday")
        self.assertFalse(day_after_thanksgiving.is_open)
        self.assertEqual(day_after_thanksgiving.reason, "after_regular_close")

    def test_backtester_reports_risk_metrics_and_next_open_trade(self):
        bars = FakeMarketData().get_stock_bars(["QQQ"], "1Day", "2026-01-01")["QQQ"]
        strategy = TechnicalStrategy(compact_strategy_config())
        result = Backtester(strategy, RiskManager(RiskConfig(max_position_pct=0.2))).run(
            {"QQQ": bars},
            starting_cash=10_000,
        )

        self.assertGreaterEqual(result.trade_count, 1)
        self.assertGreater(len(result.equity_curve), 0)
        self.assertGreater(result.ending_value, 0)
        self.assertIsInstance(result.max_drawdown_pct, float)
        self.assertIsInstance(result.sharpe_ratio, float)
        self.assertEqual(result.trades[0].timestamp, "T031")

    def test_cli_backtest_outputs_metrics_json(self):
        bars = FakeMarketData().get_stock_bars(["QQQ"], "1Day", "2026-01-01")["QQQ"]

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "config.json"
            csv_path = temp_path / "bars.csv"

            config_path.write_text(
                json.dumps(
                    {
                        "mode": "dry_run",
                        "symbols": ["QQQ"],
                        "strategy": asdict(compact_strategy_config()),
                        "risk": {
                            "max_position_pct": 0.2,
                            "min_cash_buffer_pct": 0.05,
                            "min_order_notional": 50,
                            "risk_per_trade_pct": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            csv_path.write_text(
                "symbol,timestamp,open,high,low,close,volume\n"
                + "\n".join(
                    f"{bar.symbol},{bar.timestamp},{bar.open},{bar.high},{bar.low},{bar.close},{bar.volume}"
                    for bar in bars
                ),
                encoding="utf-8",
            )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "--config",
                        str(config_path),
                        "backtest",
                        "--csv",
                        str(csv_path),
                        "--cash",
                        "10000",
                    ]
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertIn("max_drawdown_pct", payload)
        self.assertIn("sharpe_ratio", payload)
        self.assertIn("trade_count", payload)
