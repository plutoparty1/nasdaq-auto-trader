from datetime import datetime, timezone
from pathlib import Path

from nasdaq_auto_trader.config_settings import TradingSessionState
from nasdaq_auto_trader.models import Position, PositionHighWater
from nasdaq_auto_trader.session_safety_reservation import PersistedSafetyState
from nasdaq_auto_trader.session_state_persistence import (
    load_session_state,
    save_session_state,
)
from nasdaq_auto_trader.trading_session_store import TradingSessionStore


def test_observed_peak_survives_restart(tmp_path: Path) -> None:
    now = datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc)
    state = TradingSessionState()
    state.observe_position("QQQ", Position("QQQ", 1, 102, 100), now)
    state.observe_position("QQQ", Position("QQQ", 1, 103, 100), now)
    store = TradingSessionStore(tmp_path / "session.json")
    save_session_state(store, state)

    tracked = load_session_state(store).position_with_high_water(
        "QQQ",
        Position("QQQ", 1, 101.5, 100),
    )

    assert tracked is not None
    assert tracked.high_water_price == 103


def test_closed_position_removes_stale_peak(tmp_path: Path) -> None:
    now = datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc)
    state = TradingSessionState()
    state.observe_position("QQQ", Position("QQQ", 1, 103, 100), now)
    store = TradingSessionStore(tmp_path / "session.json")
    save_session_state(store, state)
    state.observe_position("QQQ", None, now)
    save_session_state(store, state)

    tracked = load_session_state(store).position_with_high_water(
        "QQQ",
        Position("QQQ", 1, 101, 100),
    )

    assert tracked is not None
    assert tracked.high_water_price is None


def test_portfolio_observation_clears_closed_symbol() -> None:
    now = datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc)
    state = TradingSessionState()
    state.observe_position("QQQ", Position("QQQ", 1, 103, 100), now)
    state.observe_position("NVDA", Position("NVDA", 1, 203, 200), now)

    state.observe_portfolio({"QQQ": Position("QQQ", 1, 104, 100)}, now)

    assert state.position_high_water == {"QQQ": PositionHighWater(100, 104)}
    assert "NVDA" not in state.position_first_seen_at


def test_invalid_active_position_preserves_closed_tombstone(tmp_path: Path) -> None:
    now = datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc)
    store = TradingSessionStore(tmp_path / "session.json")
    state = TradingSessionState()
    state.observe_position("QQQ", None, now)
    save_session_state(store, state)

    loaded = load_session_state(store)
    loaded.observe_position("QQQ", Position("QQQ", 1, 0, 0), now)
    save_session_state(store, loaded)
    persisted = load_session_state(store)

    assert persisted.position_high_water == {}
    assert persisted.closed_position_symbols == {"QQQ"}
    assert persisted.position_state_versions == {"QQQ": 1}


def test_concurrent_peak_merge_respects_trade_identity(tmp_path: Path) -> None:
    store = TradingSessionStore(tmp_path / "session.json")
    store.save_safety_state(
        PersistedSafetyState(
            market_date="2026-08-31",
            position_high_water={"QQQ": PositionHighWater(100, 103)},
        )
    )
    store.merge_safety_state(
        PersistedSafetyState(
            market_date="2026-08-31",
            position_high_water={"QQQ": PositionHighWater(100, 102)},
        )
    )
    assert store.load_safety_state().position_high_water["QQQ"].high_water_price == 103

    store.merge_safety_state(
        PersistedSafetyState(
            market_date="2026-08-31",
            position_high_water={"QQQ": PositionHighWater(101, 102)},
        )
    )
    assert store.load_safety_state().position_high_water["QQQ"] == PositionHighWater(
        101,
        102,
    )


def test_disjoint_peak_saves_preserve_both_symbols(tmp_path: Path) -> None:
    store = TradingSessionStore(tmp_path / "session.json")
    store.save_safety_state(
        PersistedSafetyState(
            market_date="2026-08-31",
            position_high_water={"QQQ": PositionHighWater(100, 103)},
        )
    )
    store.merge_safety_state(
        PersistedSafetyState(
            market_date="2026-08-31",
            position_high_water={"NVDA": PositionHighWater(200, 204)},
        )
    )

    assert store.load_safety_state().position_high_water == {
        "QQQ": PositionHighWater(100, 103),
        "NVDA": PositionHighWater(200, 204),
    }


def test_stale_writer_cannot_resurrect_closed_peak(tmp_path: Path) -> None:
    now = datetime(2026, 8, 31, 14, 30, tzinfo=timezone.utc)
    store = TradingSessionStore(tmp_path / "session.json")
    initial = TradingSessionState()
    initial.observe_position("QQQ", Position("QQQ", 1, 103, 100), now)
    save_session_state(store, initial)
    stale_writer = load_session_state(store)
    closing_writer = load_session_state(store)
    closing_writer.observe_position("QQQ", None, now)
    save_session_state(store, closing_writer)

    stale_writer.observe_position("QQQ", Position("QQQ", 1, 102, 100), now)
    save_session_state(store, stale_writer)
    after_stale_save = load_session_state(store)

    assert "QQQ" not in after_stale_save.position_high_water
    assert after_stale_save.closed_position_symbols == {"QQQ"}

    after_stale_save.observe_position("QQQ", Position("QQQ", 1, 101, 100), now)
    save_session_state(store, after_stale_save)
    reopened = load_session_state(store)
    assert reopened.position_high_water["QQQ"] == PositionHighWater(100, 101)
    assert reopened.closed_position_symbols == set()

    stale_reopened_writer = load_session_state(store)
    latest_closing_writer = load_session_state(store)
    latest_closing_writer.observe_position("QQQ", None, now)
    save_session_state(store, latest_closing_writer)

    stale_reopened_writer.observe_position(
        "QQQ",
        Position("QQQ", 1, 101, 100),
        now,
    )
    save_session_state(store, stale_reopened_writer)
    after_latest_close = load_session_state(store)

    assert "QQQ" not in after_latest_close.position_high_water
    assert after_latest_close.closed_position_symbols == {"QQQ"}
