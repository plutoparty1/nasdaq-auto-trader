from datetime import datetime, timezone
from pathlib import Path

import pytest

from nasdaq_auto_trader import operational_signal_gate as gate
from nasdaq_auto_trader.models import Action, Bar, TradeDecision
from nasdaq_auto_trader.session_claims import SignalKey
from nasdaq_auto_trader.trading_session_store import TradingSessionStore


def bar(timestamp: str) -> Bar:
    return Bar("CMCSA", timestamp, 20.61, 20.61, 20.61, 20.61, 100)


@pytest.mark.parametrize("action", ["buy", "sell", "hold"])
def test_same_bar_blocks_opposite_action_and_reentry_after_restart(tmp_path: Path, action: Action) -> None:
    store = TradingSessionStore(tmp_path / "decision_session.json")
    bars = [bar("20261009")]
    now = datetime(2026, 10, 12, 16, tzinfo=timezone.utc)
    gate.gate_decision(store, "builtin", "1", "CMCSA", bars, TradeDecision("CMCSA", "buy", 90, 20.61), now)
    restarted = TradingSessionStore(store.path)
    decision = TradeDecision("CMCSA", action, 90, 20.61)
    result = gate.gate_decision(restarted, "builtin", "1", "CMCSA", bars, decision, now)
    assert result.action == "hold"
    assert "completed_bar_already_evaluated" in result.reasons


def test_early_close_allows_completed_daily_bar() -> None:
    bars = [bar("20261127")]
    assert gate.prepare_completed_bars(bars, "1Day", datetime(2026, 11, 27, 18, tzinfo=timezone.utc)) == bars


def test_invalid_daily_timestamp_and_unsupported_interval_fail_closed() -> None:
    now = datetime(2026, 10, 13, 22, tzinfo=timezone.utc)
    assert gate.prepare_completed_bars([bar("invalid")], "1Day", now) == []
    assert gate.prepare_completed_bars([bar("20261009")], "invalid", now) == []


def test_next_completed_bar_allows_new_decision(tmp_path: Path) -> None:
    store = TradingSessionStore(tmp_path / "decision_session.json")
    now = datetime(2026, 10, 13, 22, tzinfo=timezone.utc)
    decision = TradeDecision("CMCSA", "buy", 90, 20.61)
    gate.gate_decision(store, "builtin", "1", "CMCSA", [bar("20261009")], decision, now)
    assert gate.gate_decision(store, "builtin", "1", "CMCSA", [bar("20261012")], decision, now).action == "buy"


@pytest.mark.parametrize("timestamp", ["20261012", "2026-10-12", "2026-10-12T04:00:00Z"])
def test_daily_current_session_is_incomplete_before_close(timestamp: str) -> None:
    now = datetime(2026, 10, 12, 16, tzinfo=timezone.utc)
    assert gate.prepare_completed_bars([bar("20261009"), bar(timestamp)], "1Day", now) == [bar("20261009")]


def test_daily_session_becomes_complete_at_close() -> None:
    bars = [bar("20261012")]
    assert gate.prepare_completed_bars(bars, "1Day", datetime(2026, 10, 12, 20, tzinfo=timezone.utc)) == bars


def test_intraday_filters_future_and_open_bar() -> None:
    bars = [bar("2026-10-12T15:58:00Z"), bar("2026-10-12T16:00:00Z"), bar("2026-10-12T16:01:00Z")]
    assert gate.prepare_completed_bars(bars, "1Min", datetime(2026, 10, 12, 16, tzinfo=timezone.utc)) == bars[:1]


def test_corrupt_store_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "decision_session.json"
    path.write_text("broken", encoding="utf-8")
    result = gate.gate_decision(TradingSessionStore(path), "builtin", "1", "CMCSA", [bar("20261009")], TradeDecision("CMCSA", "buy", 90, 20.61), datetime.now(timezone.utc))
    assert result.action == "hold"
    assert "session_store_corrupt" in result.reasons


def test_same_completed_bar_stays_consumed_across_market_dates(tmp_path: Path) -> None:
    store = TradingSessionStore(tmp_path / "decision_session.json")
    decision = TradeDecision("CMCSA", "buy", 90, 20.61)
    bars = [bar("20261009")]
    gate.gate_decision(store, "builtin", "1", "CMCSA", bars, decision, datetime(2026, 10, 12, 16, tzinfo=timezone.utc))
    result = gate.gate_decision(store, "builtin", "1", "CMCSA", bars, decision, datetime(2026, 10, 13, 16, tzinfo=timezone.utc))
    assert result.action == "hold"


def test_interrupted_evaluation_remains_blocked_after_restart(tmp_path: Path) -> None:
    store = TradingSessionStore(tmp_path / "decision_session.json")
    store.claim(SignalKey("2026-10-09", "builtin", "1", "CMCSA", "evaluation", "20261009"))
    restarted = TradingSessionStore(store.path)
    result = gate.gate_decision(restarted, "builtin", "1", "CMCSA", [bar("20261009")], TradeDecision("CMCSA", "sell", 90, 20.61), datetime(2026, 10, 12, 16, tzinfo=timezone.utc))
    assert result.action == "hold"
    assert "signal_key_submitting" in result.reasons
