from __future__ import annotations

from datetime import datetime, timezone

from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_runtime import apply_settings_to_app_config
from nasdaq_auto_trader.config_settings import TradingSessionState, TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, Bar, Position, PositionHighWater
from nasdaq_auto_trader.session_state_persistence import load_session_state
from nasdaq_auto_trader.strategy import TechnicalStrategy
from nasdaq_auto_trader.strategy_config import StrategyConfig
from nasdaq_auto_trader.trading_agents_types import TradingAgentsConfig
from tests.app_controller_fixtures import FakeEngineFactory, IsolatedControllerTestCase


def _bars_with_old_high(latest_price: float) -> list[Bar]:
    return [
        Bar("QQQ", "2026-08-01", 149, 150, 148, 149, 1_000),
        Bar(
            "QQQ",
            "2026-08-31",
            latest_price,
            latest_price,
            latest_price,
            latest_price,
            1_000,
        ),
    ]


def _profit_protection_strategy() -> TechnicalStrategy:
    return TechnicalStrategy(
        StrategyConfig(
            stop_loss_pct=0.5,
            take_profit_pct=0.05,
            sell_score=999,
            trailing_stop_enabled=True,
            trailing_stop_activation_pct=0.02,
            trailing_stop_pct=0.01,
        )
    )


def test_given_tracked_three_percent_peak_when_gain_retraces_then_sell() -> None:
    # Given a position that reached +3% after entry and remains profitable.
    position = Position(
        "QQQ",
        qty=1,
        market_value=101.5,
        avg_entry_price=100,
        high_water_price=103,
    )

    # When the current mark is more than 1% below that tracked peak.
    decision = _profit_protection_strategy().decide(
        "QQQ",
        _bars_with_old_high(101.5),
        position,
    )

    # Then the strategy protects the remaining gain before the 5% fixed target.
    assert decision.action == "sell"
    assert decision.reasons == ["trailing_profit_protection"]


def test_given_only_pre_entry_historical_high_when_evaluated_then_hold() -> None:
    # Given a profitable position whose tracked post-entry peak never reached +2%.
    position = Position(
        "QQQ",
        qty=1,
        market_value=101.5,
        avg_entry_price=100,
        high_water_price=101.5,
    )

    # When old daily history contains a much higher price from before entry.
    decision = _profit_protection_strategy().decide(
        "QQQ",
        _bars_with_old_high(101.5),
        position,
    )

    # Then historical bars cannot fabricate a trailing-profit sell.
    assert decision.action == "hold"
    assert "trailing_profit_protection" not in decision.reasons


def test_given_persisted_peak_when_engine_cycles_then_sell_reaches_order_path() -> None:
    # Given a restarted engine with a persisted +3% high-water mark.
    now = datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc)
    state = TradingSessionState()
    state.observe_position("QQQ", Position("QQQ", 1, 103, 100), now)
    config = AppConfig(
        mode="dry_run",
        symbols=["QQQ"],
        strategy=_profit_protection_strategy().config,
    )
    engine = TradingEngine(
        config,
        market_data=_StaticMarketData(_bars_with_old_high(101.5)),
        account=AccountSnapshot(1_000, 1_100, 1_000),
        positions={"QQQ": Position("QQQ", 1, 101.5, 100)},
        clock=lambda: now,
        trading_settings=TradingSettings(trailing_stop_enabled=True),
        trading_session_state=state,
    )

    # When a normal decision cycle evaluates the held position.
    results = engine.run_once()

    # Then profit protection produces a sell order through the real engine seam.
    assert results[0]["decision"].action == "sell"
    assert results[0]["decision"].reasons == ["trailing_profit_protection"]
    assert results[0]["order"].side == "sell"


def test_given_no_gui_settings_when_engine_cycles_then_persisted_peak_still_applies() -> None:
    # Given a direct CLI-style engine with a persisted +3% peak and no GUI settings.
    now = datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc)
    state = TradingSessionState()
    state.observe_position("QQQ", Position("QQQ", 1, 103, 100), now)
    engine = TradingEngine(
        AppConfig(
            mode="dry_run",
            symbols=["QQQ"],
            strategy=_profit_protection_strategy().config,
        ),
        market_data=_StaticMarketData(_bars_with_old_high(101.5)),
        account=AccountSnapshot(1_000, 1_100, 1_000),
        positions={"QQQ": Position("QQQ", 1, 101.5, 100)},
        clock=lambda: now,
        trading_session_state=state,
    )

    # When the normal non-GUI decision cycle runs.
    result = engine.run_once()[0]

    # Then the persisted high-water still reaches the sell order path.
    assert result["decision"].reasons == ["trailing_profit_protection"]
    assert result["order"].side == "sell"


def test_given_ai_features_when_protective_exit_is_due_then_ai_cannot_bypass_it() -> None:
    # Given AI decision features and a held position whose protected gain retraced.
    now = datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc)
    settings = TradingSettings(
        ai_trade_decision_enabled=True,
        ai_candidate_tickers=["QQQ"],
        trailing_stop_enabled=True,
    )
    state = TradingSessionState()
    state.observe_position("QQQ", Position("QQQ", 1, 103, 100), now)
    engine = TradingEngine(
        AppConfig(
            mode="dry_run",
            symbols=["QQQ"],
            strategy=_profit_protection_strategy().config,
        ),
        market_data=_StaticMarketData(_bars_with_old_high(101.5)),
        account=AccountSnapshot(1_000, 1_100, 1_000),
        positions={"QQQ": Position("QQQ", 1, 101.5, 100)},
        clock=lambda: now,
        trading_settings=settings,
        trading_session_state=state,
        ai_provider=_FailIfCalledAIProvider(),
    )

    # When the engine chooses between mandatory exits and AI recommendations.
    result = engine.run_once()[0]

    # Then the mandatory profit-protection sell runs before the AI provider.
    assert result["decision"].reasons == ["trailing_profit_protection"]
    assert result["order"].side == "sell"
    assert "ai_decision" not in result


class _FailIfCalledAIProvider:
    def request_ai_recommendation(self, prompt: str, context: dict) -> str:
        del prompt, context
        raise AssertionError("protective exits must run before AI")


def test_given_trading_agent_hold_when_protective_exit_is_due_then_sell_remains() -> None:
    now = datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc)
    state = TradingSessionState()
    state.observe_position("QQQ", Position("QQQ", 1, 103, 100), now)
    engine = TradingEngine(
        AppConfig(
            mode="dry_run",
            symbols=["QQQ"],
            strategy=_profit_protection_strategy().config,
            trading_agents=TradingAgentsConfig(
                enabled=True,
                decision_policy="replace",
            ),
        ),
        market_data=_StaticMarketData(_bars_with_old_high(101.5)),
        account=AccountSnapshot(1_000, 1_100, 1_000),
        positions={"QQQ": Position("QQQ", 1, 101.5, 100)},
        clock=lambda: now,
        trading_session_state=state,
    )

    result = engine.run_once()[0]

    assert result["decision"].reasons == ["trailing_profit_protection"]
    assert result["order"].side == "sell"
    assert result["trading_agents"] is None


class TestControllerProfitProtectionPersistence(IsolatedControllerTestCase):
    def test_given_non_auto_refresh_when_controller_restarts_then_peak_survives(self) -> None:
        # Given a non-auto controller backed by a durable session store.
        store = self.session_store()
        controller = self.create_controller(
            AppConfig(mode="dry_run", symbols=["QQQ"]),
            engine_factory=FakeEngineFactory(),
            clock=lambda: datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc),
            session_store=store,
        )

        # When the portfolio refresh observes the held position.
        controller.refresh_portfolio()

        # Then a restarted controller can load that position's high-water mark.
        reloaded = load_session_state(store)
        assert reloaded.position_high_water["QQQ"] == PositionHighWater(50, 60)


class _StaticMarketData:
    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1_000,
    ) -> dict[str, list[Bar]]:
        del timeframe, start, end, limit
        return {symbol: list(self._bars) for symbol in symbols}


def test_given_default_automatic_settings_when_applied_then_protection_is_on() -> None:
    # Given the automatic trader's default user settings.
    settings = TradingSettings()

    # When those settings are mapped to the strategy used by the engine.
    strategy = apply_settings_to_app_config(AppConfig(), settings).strategy

    # Then a 2% peak activates a 1% trailing profit guard by default.
    assert strategy.trailing_stop_enabled is True
    assert strategy.trailing_stop_activation_pct == 0.02
    assert strategy.trailing_stop_pct == 0.01
