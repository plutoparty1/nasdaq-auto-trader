import unittest

from nasdaq_auto_trader.ai_quant_lab.backtest_engine import BacktestResult
from nasdaq_auto_trader.ai_quant_lab.validation_engine import ValidationEngine


class AIQuantValidationMetricTests(unittest.TestCase):
    def test_validation_computes_advanced_overfit_metrics_for_stable_oos_curve(self):
        result = _backtest_result(_stable_equity_curve())

        validation = ValidationEngine().validate(result)

        self.assertTrue(validation.passed)
        self.assertTrue(validation.promotion_eligible)
        self.assertEqual(validation.missing_advanced_metrics, ())
        self.assertGreater(validation.metrics["purged_cross_validation_score"], 0.75)
        self.assertGreater(validation.metrics["combinatorial_purged_cross_validation_score"], 0.75)
        self.assertLess(validation.metrics["pbo_probability"], 0.25)
        self.assertGreater(validation.metrics["deflated_sharpe_ratio"], 0.10)
        self.assertLess(validation.metrics["multiple_testing_correction_penalty"], 0.20)

    def test_validation_blocks_promotion_when_advanced_evidence_is_too_short(self):
        result = _backtest_result(tuple(100_000.0 + index for index in range(40)))

        validation = ValidationEngine().validate(result)

        self.assertTrue(validation.passed)
        self.assertFalse(validation.promotion_eligible)
        self.assertIn("advanced_overfit_evidence_insufficient", validation.rejection_reasons)
        self.assertIn("pbo", validation.missing_advanced_metrics)

    def test_validation_blocks_promotion_for_unstable_oos_curve(self):
        curve = tuple(100_000.0 + ((-1) ** index) * 1_000.0 for index in range(90))
        result = _backtest_result(curve)

        validation = ValidationEngine().validate(result)

        self.assertFalse(validation.promotion_eligible)
        self.assertIn("pbo_probability_too_high", validation.rejection_reasons)
        self.assertGreaterEqual(validation.metrics["pbo_probability"], 0.35)


def _stable_equity_curve() -> tuple[float, ...]:
    return tuple(100_000.0 + index * 25.0 for index in range(90))


def _backtest_result(equity_curve: tuple[float, ...]) -> BacktestResult:
    return BacktestResult(
        experiment_id="experiment-advanced-validation",
        strategy_id="strategy-advanced-validation",
        success=True,
        metrics={
            "total_return": (equity_curve[-1] / equity_curve[0]) - 1,
            "cagr": 0.08,
            "sharpe": 1.1,
            "sortino": 1.1,
            "max_drawdown": 0.04,
            "win_rate": 0.56,
            "profit_factor": 1.4,
            "expectancy": 0.10,
            "turnover": 0.12,
            "strategy_trial_count": 3.0,
        },
        trades=(),
        equity_curve=equity_curve,
    )


if __name__ == "__main__":
    unittest.main()
