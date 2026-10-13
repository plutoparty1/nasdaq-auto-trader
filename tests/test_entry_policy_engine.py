from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_settings import TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, OrderRequest, Position
from nasdaq_auto_trader.risk import RiskConfig
from tests.test_auto_symbol_engine import AUTO_TEST_NOW, _guard, _write_paper_strategy
from tests.test_automatic_entry_eligibility import MarketData, price_bars
from tests.test_entry_policy_strategy import shared_config


class NoOrderBroker:
    def submit_order(self, order: OrderRequest) -> None:
        raise AssertionError(f"submission prohibited in isolated test: {order.side}")

    def cancel_order(self, order_id: str) -> None:
        raise AssertionError("cancellation prohibited in isolated test")


@pytest.fixture
def current_minimum_engine(tmp_path: Path) -> TradingEngine:
    paths = StrategyArtifactPaths.from_root(tmp_path)
    _write_paper_strategy(paths, top_n=1, threshold=.99)
    spec_path = paths.spec_dir / "auto-v1.json"
    spec = json.loads(spec_path.read_text())
    spec["position_sizing"]["max_single_position_pct"] = .5
    spec_path.write_text(json.dumps(spec))
    paths.ai_config_path.write_text(json.dumps({
        "max_single_position_pct": .5, "max_total_exposure_pct": .5,
    }))
    return TradingEngine(
        AppConfig(mode="dry_run", strategy=shared_config(),
                  risk=RiskConfig(order_qty=1, max_position_pct=.5)),
        broker=NoOrderBroker(),
        market_data=MarketData({
            "MSFT": price_bars("MSFT", [31.5 - index * .01 for index in range(220)]),
        }),
        account=AccountSnapshot(63.09, 63.09, 63.09), positions={},
        trading_settings=TradingSettings(auto_symbol_selection_enabled=True,
                                         daily_minimum_buy_enabled=True),
        strategy_artifact_paths=paths, automatic_order_guard=_guard(paths, tmp_path),
        clock=lambda: AUTO_TEST_NOW,
    )


def test_repaired_engine_rejects_minimum_bypass_across_repeated_cycles(
    current_minimum_engine: TradingEngine,
) -> None:
    from nasdaq_auto_trader.strategy import TechnicalStrategy

    # Given: this operational fixture has no entry signal and a qualifying exit.
    engine = current_minimum_engine
    bars = engine.market_data.bars["MSFT"]
    strategy = TechnicalStrategy(engine.config.strategy)
    flat = strategy.decide("MSFT", bars, None)
    held = strategy.decide("MSFT", bars,
                           Position("MSFT", 1, bars[-1].close, bars[-1].close))
    assert flat.action == "hold"
    assert flat.score == 0
    assert "below_long_regime" in flat.reasons
    assert held.action == "sell"
    assert held.score == 8
    assert held.score >= strategy.config.sell_score
    assert engine.trading_settings.daily_minimum_buy_enabled
    configured_risk = engine.risk_manager.config
    # When: saved minimum-buy remains enabled across successive five-minute cycles.
    results = []
    for index in range(3):
        engine._clock = lambda index=index: AUTO_TEST_NOW + timedelta(minutes=5 * index)
        results.extend(engine.run_once())
    # Then: rejected entry never creates a holding, reverse order, or reentry.
    assert results == []
    assert engine.last_selection_report.status == "no_trade"
    assert engine.trading_session_state.buy_count == 0
    assert engine.trading_session_state.sell_count == 0
    assert engine._positions == {}
    assert engine.risk_manager.config == configured_risk
    assert engine.config.strategy.stop_loss_pct == .03
    assert engine.risk_manager.config.risk_per_trade_pct == .01


@pytest.mark.parametrize("retired_flag", [False, True])
def test_disabled_minimum_is_not_bypassed_when_no_buys_or_holdings(
    current_minimum_engine: TradingEngine, retired_flag: bool,
) -> None:
    engine = current_minimum_engine
    engine.trading_settings = replace(engine.trading_settings,
                                      daily_minimum_buy_enabled=False,
                                      daily_forced_order_enabled=retired_flag)
    for _ in range(3):
        assert engine.run_once() == []
    assert engine.last_selection_report.status == "no_trade"
    assert engine.trading_session_state.buy_count == 0


def test_disabled_minimum_does_not_manufacture_second_holding(
    current_minimum_engine: TradingEngine,
) -> None:
    engine = current_minimum_engine
    engine.trading_settings = replace(engine.trading_settings,
                                      daily_minimum_buy_enabled=False)
    engine._positions = {"HELD": Position("HELD", 1, 1, 1)}
    result = engine.run_once()
    assert all(item["decision"].action != "buy" and item["order"] is None for item in result)
    assert engine.trading_session_state.buy_count == 0
