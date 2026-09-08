from dataclasses import replace
from itertools import product
from pathlib import Path

import pytest

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.config_types import BrokerName, RunMode
from nasdaq_auto_trader.config_errors import TradingModeValidationError
from nasdaq_auto_trader.engine import TradingEngine
from tests.auto_symbol_live_guard_fixtures import _LiveBroker, _live_engine, _write_champion
from tests.test_auto_symbol_engine import _guard, _write_paper_strategy


@pytest.mark.parametrize("mode", ("dry_run", "paper", "live"))
@pytest.mark.parametrize("legacy_enabled", (False, True))
def test_no_trade_never_creates_an_order(
    tmp_path: Path, mode: RunMode, legacy_enabled: bool
) -> None:
    # Given: a valid strategy whose entry threshold rejects every candidate.
    paths = StrategyArtifactPaths.from_root(tmp_path / "artifacts")
    _write_champion(paths, threshold=1.0)
    _write_paper_strategy(paths, threshold=1.0)
    broker = _LiveBroker("accepted")
    engine = _live_engine(paths, _guard(paths, tmp_path), broker, daily_forced=True)
    engine.config = replace(engine.config, mode=mode)
    engine.trading_settings = replace(
        engine.trading_settings, daily_forced_order_enabled=legacy_enabled
    )

    # When: the automatic engine runs during the regular market session.
    results = engine.run_once()

    # Then: neither simulated nor broker orders are manufactured.
    assert engine.last_selection_report.status == "no_trade"
    assert results == []
    assert broker.orders == []
    assert engine.trading_session_state.buy_count == 0
    assert engine.trading_session_state.sell_count == 0


@pytest.mark.parametrize("broker_name", ("kis", "alpaca"))
@pytest.mark.parametrize(
    "legacy,session,unattended,live", tuple(product((False, True), repeat=4))
)
def test_automatic_session_requires_explicit_authorization_flags(
    tmp_path: Path,
    broker_name: BrokerName,
    legacy: bool,
    session: bool,
    unattended: bool,
    live: bool,
) -> None:
    # Given: all combinations of saved legacy and current authorization flags.
    paths = StrategyArtifactPaths.from_root(tmp_path / "artifacts")
    _write_champion(paths)
    broker = _LiveBroker("accepted")
    guard = _guard(paths, tmp_path)
    engine = _live_engine(
        paths, guard, broker, issue_authorization=False, daily_forced=True
    )
    engine.config = replace(engine.config, broker=broker_name)
    engine.trading_settings = replace(
        engine.trading_settings,
        daily_forced_order_enabled=legacy,
        automatic_session_authorization_enabled=session,
        unattended_operation_enabled=unattended,
        unattended_live_trading_enabled=live,
    )

    # When: a valid ordinary entry is evaluated without an existing authorization.
    results = engine.run_once()

    # Then: only explicit KIS unattended live authorization permits the order.
    allowed = session and unattended and live and broker_name == "kis"
    assert len(broker.orders) == int(allowed)
    if allowed:
        assert len(results) == 1
        stored = guard.authorization_store.load()
        assert stored is not None
        assert stored.envelope.purpose == "automatic"
    else:
        assert results == []
        assert guard.authorization_store.load() is None


@pytest.mark.parametrize("flag", ("allow_live_trading", "live_environment_authorized"))
def test_automatic_session_cannot_bypass_runtime_live_authorization(
    tmp_path: Path, flag: str
) -> None:
    # Given: explicit unattended settings but a disabled runtime live safeguard.
    paths = StrategyArtifactPaths.from_root(tmp_path / "artifacts")
    _write_champion(paths)
    broker = _LiveBroker("accepted")
    engine = _live_engine(
        paths, _guard(paths, tmp_path), broker,
        issue_authorization=False, daily_forced=True,
    )
    settings = replace(
        engine.trading_settings, daily_forced_order_enabled=False
    )

    # When: the engine is constructed with a disabled live safeguard.
    with pytest.raises(TradingModeValidationError):
        TradingEngine(
            replace(engine.config, **{flag: False}),
            broker=broker,
            market_data=engine.market_data,
            trading_settings=settings,
            strategy_artifact_paths=paths,
            automatic_order_guard=engine.automatic_order_guard,
        )

    # Then: the broker is never called and live authorization remains blocked.
    assert broker.orders == []
    assert engine.automatic_order_guard.authorization_store.load() is None
