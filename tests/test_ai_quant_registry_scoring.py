import tempfile
import unittest
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.scoring_engine import StrategyScore
from tests.ai_quant_fixtures import valid_spec


class AIQuantRegistryScoringTests(unittest.TestCase):
    def test_registry_rejects_score_without_promotion_recommendation(self):
        spec = valid_spec()
        score = StrategyScore(0.64, {}, (), False)
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = StrategyRegistry(
                Path(temp_dir) / "registry.json",
                Path(temp_dir) / "promoted.json",
            )

            decision = registry.evaluate_promotion(spec, score)

        self.assertFalse(decision.allowed)
        self.assertIn("promotion_score_below_threshold", decision.reasons)


if __name__ == "__main__":
    unittest.main()
