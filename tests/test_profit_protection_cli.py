from datetime import datetime, timezone
from unittest.mock import patch

from nasdaq_auto_trader.cli_commands_basic import _run_once
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_settings import TradingSessionState
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.models import AccountSnapshot, Position
from nasdaq_auto_trader.session_state_persistence import save_session_state
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.test_profit_protection import (
    _StaticMarketData,
    _bars_with_old_high,
    _profit_protection_strategy,
)


def test_direct_cli_loads_and_persists_profit_high_water(tmp_path) -> None:
    now = datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc)
    store = TradingSessionStore(tmp_path / "runtime" / "trading_session.json")
    state = TradingSessionState()
    state.observe_position("QQQ", Position("QQQ", 1, 103, 100), now)
    save_session_state(store, state)
    config = AppConfig(
        mode="dry_run",
        symbols=["QQQ"],
        strategy=_profit_protection_strategy().config,
    )

    def engine_factory(runtime_config, **kwargs):
        return TradingEngine(
            runtime_config,
            market_data=_StaticMarketData(_bars_with_old_high(101.5)),
            account=AccountSnapshot(1_000, 1_100, 1_000),
            positions={"QQQ": Position("QQQ", 1, 101.5, 100)},
            clock=lambda: now,
            **kwargs,
        )

    with patch(
        "nasdaq_auto_trader.cli_commands_basic.application_data_root",
        return_value=tmp_path,
    ), patch(
        "nasdaq_auto_trader.cli_commands_basic.TradingEngine",
        side_effect=engine_factory,
    ):
        [result] = _run_once(config)

    assert result["decision"]["reasons"] == ["trailing_profit_protection"]
    assert result["order"]["side"] == "sell"
    assert store.load_safety_state().position_high_water["QQQ"].high_water_price == 103
