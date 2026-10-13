from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nasdaq_auto_trader.config_settings import TradingSessionState
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.production_baseline import ProductionBaselineStore


def test_restart_restores_original_daily_equity_when_current_equity_fell(tmp_path: Path) -> None:
    # Given: an original $1000 baseline persisted before a restart.
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"account_digest": "sandbox", "market_date": "2026-10-13",
                                "starting_equity": 1000.0}), encoding="utf-8")
    state = TradingSessionState(market_date="2026-10-13", daily_loss_state_unavailable=True)
    store = ProductionBaselineStore(path, "sandbox")
    # When: today's account is restored at $970.
    reason = store.restore(state, AccountSnapshot(970, 970, 970), datetime(2026, 10, 13, 15, tzinfo=UTC))
    # Then: the loss budget is measured from $1000, never reset to $970.
    assert reason == ""
    assert state.starting_equity == 1000
    assert state.daily_loss_state_unavailable is False


@pytest.mark.parametrize("payload", [None, [], {}, {"market_date": "2026-10-12"},
    {"account_digest": "other-account", "market_date": "2026-10-12", "starting_equity": 1000},
    {"account_digest": "sandbox", "market_date": "2026-10-14", "starting_equity": 1000},
])
def test_corrupt_baseline_never_resets_daily_loss_when_readable_json(
    tmp_path: Path, payload: str | float | dict[str, str | float] | list[str] | None,
) -> None:
    # Given: a present baseline file with invalid provenance or shape.
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    state = TradingSessionState()
    # When: production tries to restore the baseline.
    reason = ProductionBaselineStore(path, "sandbox").restore(
        state, AccountSnapshot(1000, 1000, 1000), datetime(2026, 10, 13, 15, tzinfo=UTC),
    )
    # Then: a malformed file cannot create a fresh favorable loss baseline.
    assert reason == "production_daily_baseline_corrupt"
    assert state.starting_equity is None


def test_missing_baseline_stays_blocked_when_session_already_observed(tmp_path: Path) -> None:
    # Given: persisted safety state says a baseline existed but its equity file is missing.
    state = TradingSessionState(market_date="2026-10-13", daily_loss_state_unavailable=True)
    # When: restart attempts to establish a new baseline from current funds.
    reason = ProductionBaselineStore(tmp_path / "missing.json", "sandbox").restore(
        state, AccountSnapshot(1000, 1000, 1000), datetime(2026, 10, 13, 15, tzinfo=UTC),
    )
    # Then: restarting cannot erase an unverified daily loss.
    assert reason == "daily_loss_state_unavailable"
