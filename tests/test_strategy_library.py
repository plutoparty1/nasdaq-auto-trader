import unittest

from tests.ai_quant_fixtures import bars

from nasdaq_auto_trader.ai_quant_lab.strategy_schema import (
    EntryRule,
    ExitRule,
    PositionSizingSpec,
    ResearchBasis,
    RiskControls,
    SignalSpec,
    SignalType,
    StrategyFamily,
    StrategySpec,
)
from nasdaq_auto_trader.quant_data.features import calculate_feature_rows
from nasdaq_auto_trader.strategies.strategy_library import build_strategy


class StrategyLibraryTests(unittest.TestCase):
    def test_strategy_generates_reasons_for_every_signal_type(self):
        signal_types = tuple(SignalType)
        spec = StrategySpec(
            strategy_id="all-signal-types",
            version="v1",
            strategy_family=StrategyFamily.ENSEMBLE,
            description="all current signal types",
            research_basis=ResearchBasis(
                provider="test",
                research_ids=("research-1",),
                source_ids=("source-1",),
                summary="test coverage",
            ),
            signals=tuple(SignalSpec(signal_type, 1.0) for signal_type in signal_types),
            entry_rule=EntryRule("weighted_score", threshold=0.0, top_n=1),
            exit_rule=ExitRule("atr_multiple", 2.0, "atr_multiple", 3.0, True, 10),
            position_sizing=PositionSizingSpec("volatility_target", 0.005, True, 0.05),
            risk_controls=RiskControls(True, True, True, True, True),
            created_at="2026-07-02T00:00:00+09:00",
            raw={},
        )
        strategy = build_strategy(spec)
        features = calculate_feature_rows({"QQQ": bars("QQQ")})

        required_features = strategy.required_features()
        signals = strategy.generate_signals(features)

        self.assertIn("atr_14", required_features)
        self.assertIn("time_series_momentum", required_features)
        self.assertEqual(len(signals), 1)
        self.assertEqual(len(signals[0].reasons), len(signal_types))
        self.assertEqual(
            {reason.split(":", 1)[0] for reason in signals[0].reasons},
            {signal_type.value for signal_type in signal_types},
        )


if __name__ == "__main__":
    unittest.main()
