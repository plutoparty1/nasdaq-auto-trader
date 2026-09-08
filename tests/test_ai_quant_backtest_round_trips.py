import unittest
from dataclasses import replace
from datetime import date, timedelta

from nasdaq_auto_trader.ai_quant_lab.backtest_engine import (
    BacktestEngine,
    BacktestRequest,
    TradeLog,
)
from nasdaq_auto_trader.ai_quant_lab.backtest_metrics import calculate_backtest_metrics
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import SignalSpec, SignalType
from tests.ai_quant_fixtures import bars, valid_spec


class AIQuantBacktestRoundTripTests(unittest.TestCase):
    def test_backtest_closes_positions_and_reports_realized_performance(self):
        request = BacktestRequest(
            valid_spec(),
            {
                "QQQ": bars("QQQ"),
                "AAPL": bars("AAPL"),
            },
        )

        result = BacktestEngine(AIQuantConfig()).run(request)

        buy_count = sum(trade.side == "buy" for trade in result.trades)
        sell_count = sum(trade.side == "sell" for trade in result.trades)
        self.assertGreater(buy_count, 0)
        self.assertEqual(sell_count, buy_count)
        self.assertLess(buy_count, 30)
        self.assertGreater(
            max(trade.qty for trade in result.trades if trade.side == "buy"),
            1,
        )
        self.assertEqual(result.metrics["win_rate"], 1.0)
        self.assertEqual(result.metrics["profit_factor"], 0.0)
        self.assertEqual(result.metrics["profit_factor_available"], 0.0)
        self.assertGreater(result.metrics["expectancy"], 0)
        self.assertGreater(result.metrics["turnover"], 0.5)

    def test_metrics_use_realized_dollar_profit_and_round_trip_count(self):
        trades = (
            TradeLog("AAPL", "buy", "1", 100.0, 1, 100.0),
            TradeLog("AAPL", "sell", "2", 120.0, 1, 120.0),
            TradeLog("MSFT", "buy", "1", 1000.0, 1, 1000.0),
            TradeLog("MSFT", "sell", "2", 999.0, 1, 999.0),
        )

        metrics = calculate_backtest_metrics((10_000.0, 10_020.0, 10_019.0), trades)

        self.assertEqual(metrics.profit_factor, 20.0)
        self.assertEqual(metrics.trade_count, 2.0)

    def test_backtest_rejects_invalid_cash_and_misaligned_timestamps(self):
        aligned = bars("QQQ")
        shifted = [
            replace(
                item,
                symbol="AAPL",
                timestamp=(
                    date.fromisoformat(item.timestamp) + timedelta(days=1)
                ).isoformat(),
            )
            for item in bars("AAPL")
        ]

        invalid_cash = BacktestEngine().run(
            BacktestRequest(valid_spec(), {"QQQ": aligned}, initial_cash=0.0)
        )
        misaligned = BacktestEngine().run(
            BacktestRequest(valid_spec(), {"QQQ": aligned, "AAPL": shifted})
        )

        self.assertFalse(invalid_cash.success)
        self.assertEqual(invalid_cash.rejection_reasons, ("initial_cash_invalid",))
        self.assertFalse(misaligned.success)
        self.assertEqual(
            misaligned.rejection_reasons,
            ("market_data_timestamps_misaligned",),
        )

    def test_exit_does_not_reopen_symbol_at_same_fill_timestamp(self):
        result = BacktestEngine(AIQuantConfig()).run(
            BacktestRequest(
                valid_spec(),
                {"QQQ": bars("QQQ"), "AAPL": bars("AAPL")},
            )
        )
        immediate_reentries = [
            (left, right)
            for left, right in zip(result.trades, result.trades[1:])
            if left.side == "sell"
            and right.side == "buy"
            and left.symbol == right.symbol
            and left.timestamp == right.timestamp
        ]

        self.assertEqual(immediate_reentries, [])

    def test_invalid_equity_curve_returns_finite_zero_metrics(self):
        for curve in ((0.0, 0.0), (100.0, float("inf")), (100.0, float("nan"))):
            with self.subTest(curve=curve):
                metrics = calculate_backtest_metrics(curve, ())
                self.assertEqual(metrics.total_return, 0.0)
                self.assertEqual(metrics.max_drawdown, 0.0)
                self.assertEqual(metrics.trade_count, 0.0)

    def test_next_open_quantity_does_not_use_unseen_close(self):
        qqq = bars("QQQ")
        aapl = bars("AAPL")
        altered_aapl = [*aapl]
        altered_aapl[2] = replace(altered_aapl[2], close=1_000.0)
        spec = valid_spec()
        spec = replace(
            spec,
            signals=(SignalSpec(SignalType.VOLATILITY_TARGETING, 1.0, {}),),
            entry_rule=replace(spec.entry_rule, threshold=0.0, top_n=2),
        )

        baseline = BacktestEngine().run(
            BacktestRequest(spec, {"QQQ": qqq, "AAPL": aapl})
        )
        altered = BacktestEngine().run(
            BacktestRequest(
                spec,
                {"QQQ": qqq, "AAPL": altered_aapl},
            )
        )
        baseline_buy = next(
            trade
            for trade in baseline.trades
            if trade.symbol == "QQQ" and trade.side == "buy"
        )
        altered_buy = next(
            trade
            for trade in altered.trades
            if trade.symbol == "QQQ"
            and trade.side == "buy"
            and trade.timestamp == baseline_buy.timestamp
        )

        self.assertEqual(altered_buy.qty, baseline_buy.qty)

    def test_backtest_rejects_invalid_and_chronologically_reversed_timestamps(self):
        invalid = [*bars("QQQ")]
        invalid[0] = replace(invalid[0], timestamp="2026-01-78")
        reversed_time = [*bars("QQQ")]
        reversed_time[0] = replace(
            reversed_time[0],
            timestamp="2026-01-01T23:00:00-05:00",
        )
        reversed_time[1] = replace(
            reversed_time[1],
            timestamp="2026-01-02T01:00:00+00:00",
        )

        invalid_result = BacktestEngine().run(
            BacktestRequest(valid_spec(), {"QQQ": invalid})
        )
        reversed_result = BacktestEngine().run(
            BacktestRequest(valid_spec(), {"QQQ": reversed_time})
        )

        self.assertEqual(
            invalid_result.rejection_reasons,
            ("market_data_timestamp_invalid",),
        )
        self.assertEqual(
            reversed_result.rejection_reasons,
            ("market_data_timestamps_not_monotonic",),
        )


if __name__ == "__main__":
    unittest.main()
