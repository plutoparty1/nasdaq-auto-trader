import unittest
import tempfile
import json
from pathlib import Path

from nasdaq_auto_trader.automatic_risk import (
    AutomaticRiskBlock,
    AutomaticRiskLimits,
    CycleReservationLedger,
    resolve_automatic_risk_limits,
)
from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSessionState, TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.risk import RiskConfig
from nasdaq_auto_trader.quant_data.symbol_selector import ResolvedStrategy, resolve_strategy
from nasdaq_auto_trader.models import (
    AccountSnapshot,
    OrderRequest,
    Position,
    TradeDecision,
)
from tests.config_engine_fixtures import compact_strategy_config
from tests.test_auto_symbol_engine import (
    AUTO_TEST_NOW,
    _AcceptedBroker,
    _AutoMarketData,
    _write_paper_strategy,
)


class AutoSymbolRiskPrecisionTests(unittest.TestCase):
    def test_zero_learned_daily_order_limit_is_unlimited(self):
        limits = AutomaticRiskLimits(0.5, 0.5, 1_000, 0, 0.01, 0.02)

        _, reason = CycleReservationLedger().apply_limits(
            OrderRequest("AAPL", "buy", qty=1),
            _decision(),
            100,
            AccountSnapshot(10_000, 10_000, 10_000),
            {},
            limits,
            100,
            10_000,
        )

        self.assertEqual(reason, "")

    def test_nonfinite_position_exposure_blocks_order(self):
        ledger = CycleReservationLedger()
        order = OrderRequest("AAPL", "buy", notional=100)

        _, reason = ledger.apply_limits(
            order,
            _decision(),
            100,
            AccountSnapshot(10_000, 10_000, 10_000),
            {"MSFT": Position("MSFT", 1, float("nan"), 100)},
            _limits(),
            0,
            10_000,
        )

        self.assertEqual(reason, "learned_exposure_state_unavailable")

    def test_notional_cap_rounds_down_without_exceeding_limit(self):
        ledger = CycleReservationLedger()
        limits = AutomaticRiskLimits(
            max_single_position_pct=1,
            max_total_exposure_pct=1,
            max_order_notional=0.019,
            max_orders_per_day=5,
            risk_per_trade_pct=1,
        )

        constrained, reason = ledger.apply_limits(
            OrderRequest("AAPL", "buy", notional=100),
            _decision(),
            100,
            AccountSnapshot(10_000, 10_000, 10_000),
            {},
            limits,
            0,
            10_000,
        )

        self.assertEqual(reason, "")
        self.assertLessEqual(constrained.notional, limits.max_order_notional)

    def test_nonfinite_account_resources_block_automatic_buy(self):
        for account in (
            AccountSnapshot(float("nan"), 10_000, 10_000),
            AccountSnapshot(10_000, 10_000, float("inf")),
        ):
            with self.subTest(account=account):
                _, reason = CycleReservationLedger().apply_limits(
                    OrderRequest("AAPL", "buy", qty=1),
                    _decision(),
                    100,
                    account,
                    {},
                    _limits(),
                    0,
                    10_000,
                )

                self.assertEqual(reason, "learned_exposure_state_unavailable")

    def test_learned_daily_loss_limit_blocks_before_order(self):
        limits = AutomaticRiskLimits(0.5, 0.5, 1_000, 5, 0.01, 0.02)

        _, reason = CycleReservationLedger().apply_limits(
            OrderRequest("AAPL", "buy", qty=1),
            _decision(),
            100,
            AccountSnapshot(9_700, 9_700, 9_700),
            {},
            limits,
            0,
            10_000,
        )

        self.assertEqual(reason, "learned_daily_loss_limit_reached")

    def test_corrupt_ai_quant_config_blocks_instead_of_using_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_paper_strategy(paths)
            paths.ai_config_path.write_text("{broken", encoding="utf-8")
            resolved = resolve_strategy("paper", paths)
            self.assertIsInstance(resolved, ResolvedStrategy)

            limits = resolve_automatic_risk_limits(paths, resolved)

        self.assertIsInstance(limits, AutomaticRiskBlock)
        self.assertEqual(limits.reason, "ai_quant_config_invalid")

    def test_learned_daily_loss_breach_latches_session_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = StrategyArtifactPaths.from_root(Path(temp_dir))
            _write_paper_strategy(paths, top_n=1)
            paths.ai_config_path.write_text(
                json.dumps(
                    {
                        "max_single_position_pct": 0.5,
                        "max_total_exposure_pct": 0.5,
                        "max_order_notional": 1000,
                        "max_orders_per_day": 5,
                        "max_daily_loss_pct": 0.02,
                    }
                ),
                encoding="utf-8",
            )
            state = TradingSessionState(starting_equity=10_000)
            broker = _AcceptedBroker()
            engine = TradingEngine(
                AppConfig(
                    mode="dry_run",
                    strategy=compact_strategy_config(),
                    risk=RiskConfig(order_qty=1, max_position_qty=10),
                ),
                broker=broker,
                market_data=_AutoMarketData(
                    account=AccountSnapshot(9_700, 9_700, 9_700)
                ),
                trading_settings=TradingSettings(
                    auto_symbol_selection_enabled=True,
                    max_daily_buy_count=10,
                    max_position_qty=10,
                    require_confirm_before_buy=False,
                ),
                trading_session_state=state,
                strategy_artifact_paths=paths,
                clock=lambda: AUTO_TEST_NOW,
            )

            engine.run_once()

        self.assertEqual(broker.orders, [])
        self.assertTrue(state.daily_loss_breached)


def _decision() -> TradeDecision:
    return TradeDecision("AAPL", "buy", 1, 100, [])


def _limits() -> AutomaticRiskLimits:
    return AutomaticRiskLimits(0.05, 0.30, 1_000, 5, 0.005)


if __name__ == "__main__":
    unittest.main()
