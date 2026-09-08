import unittest

from nasdaq_auto_trader.ai_quant_lab.backtest_engine import BacktestResult
from nasdaq_auto_trader.ai_quant_lab.validation_engine import ValidationEngine


class AIQuantValidationMetricTests(unittest.TestCase):
    def test_validation_does_not_infer_advanced_evidence_from_stable_curve(self):
        result = _backtest_result(_stable_equity_curve())

        validation = ValidationEngine().validate(result)

        self.assertTrue(validation.passed)
        self.assertFalse(validation.promotion_eligible)
        self.assertIn("independent_validation_required", validation.rejection_reasons)
        self.assertEqual(len(validation.missing_advanced_metrics), 5)
        self.assertEqual(validation.metrics["purged_cross_validation_score"], 0.0)
        self.assertEqual(validation.metrics["combinatorial_purged_cross_validation_score"], 0.0)
        self.assertEqual(validation.metrics["pbo_probability"], 1.0)
        self.assertEqual(validation.metrics["deflated_sharpe_ratio"], 0.0)
        self.assertEqual(validation.metrics["multiple_testing_correction_penalty"], 1.0)

    def test_validation_blocks_promotion_when_advanced_evidence_is_too_short(self):
        result = _backtest_result(tuple(100_000.0 + index for index in range(40)))

        validation = ValidationEngine().validate(result)

        self.assertTrue(validation.passed)
        self.assertFalse(validation.promotion_eligible)
        self.assertIn("independent_validation_required", validation.rejection_reasons)
        self.assertIn("pbo", validation.missing_advanced_metrics)

    def test_validation_blocks_unstable_curve_without_claiming_measured_pbo(self):
        curve = tuple(100_000.0 + ((-1) ** index) * 1_000.0 for index in range(90))
        result = _backtest_result(curve)

        validation = ValidationEngine().validate(result)

        self.assertFalse(validation.promotion_eligible)
        self.assertIn("independent_validation_required", validation.rejection_reasons)
        self.assertIn("pbo", validation.missing_advanced_metrics)
        self.assertNotIn("pbo_probability_too_high", validation.rejection_reasons)


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
