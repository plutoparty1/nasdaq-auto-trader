import json
from dataclasses import replace
from pathlib import Path
from typing import Literal, assert_never

import pytest

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.automatic_order_guard import AutomaticOrderGuard
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.auto_symbol_live_guard_fixtures import (
    _live_engine,
    _LiveBroker,
    _write_champion,
)


@pytest.mark.parametrize("block", ["learned_order_limit", "learned_loss", "confirmation"])
def test_session_guard_retains_ranked_decision_and_audits_without_order_intent(
    tmp_path: Path, block: Literal["learned_order_limit", "learned_loss", "confirmation"],
) -> None:
    # Given: a session-wide rule blocks every otherwise feasible buy.
    paths = StrategyArtifactPaths.from_root(tmp_path / "artifacts")
    _write_champion(paths)
    assert paths.ai_config_path is not None
    paths.ai_config_path.write_text(json.dumps({"max_orders_per_day": 1}), encoding="utf-8")
    audit = NullAuditLogger()
    broker = _LiveBroker("accepted")
    guard = AutomaticOrderGuard(paths, TradingSessionStore(tmp_path / "session.json"), audit)
    engine = _live_engine(paths, guard, broker, max_attempts=1)
    match block:
        case "learned_order_limit":
            engine.trading_session_state.buy_count = 1
            reason = "learned_daily_order_limit_reached"
        case "learned_loss":
            engine.trading_session_state.starting_equity = 10400
            reason = "learned_daily_loss_limit_reached"
        case "confirmation":
            assert engine.trading_settings is not None
            engine.trading_settings = replace(engine.trading_settings, require_confirm_before_buy=True)
            reason = "buy_confirmation_required"
        case unreachable:
            assert_never(unreachable)

    # When
    results = engine.run_once()

    # Then: the final guard records the precise block without spending an attempt.
    assert engine.last_selection_report is not None
    assert engine.last_selection_report.status == "selected"
    assert len(results) == 1
    assert results[0]["response"]["reason"] == reason
    assert [event.event_type for event in audit.events] == ["automatic_order_blocked"]
    assert audit.events[0].payload["reason"] == reason
    authorization = guard.authorization_store.load()
    assert authorization is not None
    assert authorization.attempts == 0
    assert broker.orders == []
    assert engine.trading_session_state.daily_loss_breached == (block == "learned_loss")
