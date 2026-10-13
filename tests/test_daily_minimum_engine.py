import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSessionState, TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.risk import RiskConfig, RiskManager
from tests.test_auto_symbol_engine import (
    AUTO_TEST_NOW,
    _AcceptedBroker,
    _guard,
    _write_paper_strategy,
)
from tests.test_automatic_entry_eligibility import MarketData, price_bars


@pytest.fixture
def daily_engine(tmp_path: Path) -> TradingEngine:
    paths = StrategyArtifactPaths.from_root(tmp_path)
    _write_paper_strategy(paths, top_n=2, threshold=.99)
    bars = {
        "AAPL": price_bars("AAPL", [100. + index for index in range(220)]),
        "MSFT": price_bars("MSFT", [2. + index * .01 for index in range(220)]),
        "NVDA": price_bars("NVDA", [2. + index * .005 for index in range(220)]),
    }
    return TradingEngine(
        AppConfig(risk=RiskConfig(order_qty=1)),
        broker=_AcceptedBroker(), market_data=MarketData(bars),
        account=AccountSnapshot(100, 100, 100),
        trading_settings=TradingSettings(
            auto_symbol_selection_enabled=True, daily_minimum_buy_enabled=True,
        ),
        strategy_artifact_paths=paths, automatic_order_guard=_guard(paths, tmp_path),
        clock=lambda: AUTO_TEST_NOW,
    )


def test_daily_minimum_cannot_bypass_normal_selection_threshold(daily_engine):
    # Given: the learned strategy threshold rejects all otherwise affordable shares.
    configured_risk = daily_engine.risk_manager.config
    # When: the saved minimum-buy setting is active.
    results = daily_engine.run_once()
    # Then: zero trades preserves both signal rejection and the configured budget.
    assert results == []
    assert daily_engine.broker.orders == []
    assert daily_engine.risk_manager.config == configured_risk


def test_daily_minimum_does_not_repeat_after_simulated_buy(daily_engine):
    daily_engine.trading_session_state = TradingSessionState(
        market_date=AUTO_TEST_NOW.date().isoformat(), buy_count=1,
    )

    assert daily_engine.run_once() == []


def test_next_market_day_cannot_turn_rejected_signals_into_buy(daily_engine):
    daily_engine.trading_session_state = TradingSessionState(
        market_date=(AUTO_TEST_NOW - timedelta(days=1)).date().isoformat(), buy_count=1,
    )

    assert daily_engine.run_once() == []
    assert daily_engine.broker.orders == []


@pytest.mark.parametrize("limit", ["cash", "daily_loss", "sell_only"])
def test_daily_minimum_respects_final_safety_limits(daily_engine, limit: str):
    if limit == "cash":
        daily_engine._account = AccountSnapshot(0, 100, 100)
    elif limit == "daily_loss":
        daily_engine.trading_session_state.daily_loss_breached = True
    else:
        daily_engine.trading_settings = replace(daily_engine.trading_settings, sell_only=True)

    results = daily_engine.run_once()

    assert all(item["response"]["status"] == "blocked" for item in results)
    assert daily_engine.broker.orders == []


def test_daily_policy_disabled_keeps_normal_no_trade(daily_engine):
    daily_engine.trading_settings = replace(
        daily_engine.trading_settings, daily_minimum_buy_enabled=False,
    )

    assert daily_engine.run_once() == []


def test_minimum_share_cannot_raise_one_percent_risk_budget(daily_engine):
    _write_paper_strategy(daily_engine.strategy_artifact_paths, top_n=1, threshold=0)
    spec_path = daily_engine.strategy_artifact_paths.spec_dir / "auto-v1.json"
    spec = json.loads(spec_path.read_text())
    spec["position_sizing"]["max_single_position_pct"] = .5
    spec_path.write_text(json.dumps(spec))
    daily_engine.strategy_artifact_paths.ai_config_path.write_text(json.dumps({
        "max_single_position_pct": .5, "max_total_exposure_pct": .5,
    }))
    daily_engine._account = AccountSnapshot(63.09, 63.09, 63.09)
    daily_engine.config = replace(
        daily_engine.config,
        risk=replace(daily_engine.config.risk, max_position_pct=.5),
    )
    daily_engine.risk_manager = RiskManager(daily_engine.config.risk)
    daily_engine.market_data = MarketData({
        "WBD": price_bars("WBD", [25. + index * .01 for index in range(220)]),
    })

    results = daily_engine.run_once()

    assert results == []
    assert daily_engine.broker.orders == []
    assert daily_engine.config.risk.risk_per_trade_pct == .01
    assert daily_engine.risk_manager.config.risk_per_trade_pct == .01
    assert daily_engine.run_once() == []


def test_valid_normal_signal_still_buys_with_minimum_setting_enabled(daily_engine):
    # Given: normal learned and technical entry requirements are satisfied.
    _write_paper_strategy(daily_engine.strategy_artifact_paths, top_n=1, threshold=0)
    daily_engine.market_data = MarketData({
        "MSFT": price_bars("MSFT", [2. + index * .01 for index in range(220)]),
    })
    # When: a normal affordable entry is evaluated with minimum-buy enabled.
    results = daily_engine.run_once()
    # Then: the valid signal creates one simulated buy while real orders stay blocked.
    assert len(results) == 1
    assert results[0]["decision"].action == "buy"
    assert "daily_minimum_best_affordable" not in results[0]["decision"].reasons
    assert results[0]["response"]["status"] == "dry_run"
    assert daily_engine.broker.orders == []
