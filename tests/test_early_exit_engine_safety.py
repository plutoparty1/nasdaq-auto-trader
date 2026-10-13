from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.automatic_order_pending import (
    PendingOrderCheck,
    automatic_pending_order_block,
)
from nasdaq_auto_trader.automatic_order_types import AutomaticOrderBlock
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_runtime import validate_order_against_settings
from nasdaq_auto_trader.config_settings import TradingSessionState, TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.engine_errors import PreOrderCycleError
from nasdaq_auto_trader.models import AccountSnapshot, Bar, OrderRequest, Position
from nasdaq_auto_trader.session_claims import ClaimStatus, SignalKey
from nasdaq_auto_trader.session_safety_reservation import SafetyReservationRequest
from nasdaq_auto_trader.trading_session_store import TradingSessionStore
from tests.config_engine_fixtures import compact_strategy_config
from tests.test_auto_symbol_engine import AUTO_TEST_NOW, _AutoMarketData, _guard


@dataclass(frozen=True, slots=True)
class _NeverSubmitBroker:
    pending: tuple[OrderRequest, ...] = ()

    def submit_order(self, order: OrderRequest) -> None:
        raise AssertionError(f"dry-run must not submit {order.side}")

    def list_open_orders(self) -> list[OrderRequest]:
        return list(self.pending)


class _UnavailableBuyingPowerMarket(_AutoMarketData):
    def get_overseas_buying_power(self, symbol: str, price: float) -> float:
        del symbol, price
        raise OSError("buying-power endpoint unavailable")


@pytest.fixture
def protected_engine(tmp_path: Path) -> TradingEngine:
    paths = StrategyArtifactPaths.from_root(tmp_path)
    return TradingEngine(
        AppConfig(
            broker="kis",
            mode="dry_run",
            symbols=["HELD"],
            timeframe="1Day",
            strategy=compact_strategy_config(stop_loss_pct=0.05),
        ),
        broker=_NeverSubmitBroker(),
        market_data=_UnavailableBuyingPowerMarket(
            account=AccountSnapshot(100, 194, 100),
            positions={"HELD": Position("HELD", 1, 94, 100)},
            close_by_symbol={"HELD": 94},
        ),
        trading_settings=TradingSettings(),
        trading_session_state=TradingSessionState(),
        strategy_artifact_paths=paths,
        automatic_order_guard=_guard(paths, tmp_path),
        clock=lambda: AUTO_TEST_NOW,
    )


def test_protective_sell_survives_buying_power_outage(
    protected_engine: TradingEngine,
) -> None:
    # Given a held 1-share position below its hard stop and unavailable buy sizing.
    # When the real rule cycle reaches its normal dry-run submission boundary.
    [result] = protected_engine.run_once()

    # Then protection retains account checks without calling buy-only information.
    assert result["decision"].reasons == ["fixed_stop_loss"]
    assert result["order"].side == "sell"
    assert result["order"].qty == 1
    assert result["response"]["status"] == "dry_run"
    assert result["response"]["submitted_order"] is False
    assert result["account"] == AccountSnapshot(100, 194, 100)
    assert result["buying_power_check"] is None


def test_diagnostics_cannot_invalidate_protective_order_after_submission(
    protected_engine: TradingEngine,
) -> None:
    bars = [Bar("HELD", str(index), 94, 94, 94, 94, 100) for index in range(40)]
    bars[-11] = Bar("HELD", "29", 0, 94, 0, 0, 100)
    with patch.object(protected_engine, "_load_recent_bars", return_value={"HELD": bars}), patch.object(
        protected_engine, "_submit_or_block_order", wraps=protected_engine._submit_or_block_order,
    ) as submit:
        [result] = protected_engine.run_once()
    assert submit.call_count == 1
    assert result["response"]["status"] == "dry_run"
    assert result["decision"].reasons == ["fixed_stop_loss"]
    assert result["exit_diagnostics"].buy_score is None
    assert result["exit_diagnostics"].indicator_status == "invalid_indicator_history"


def test_selector_failure_still_blocks_automatic_protection(
    protected_engine: TradingEngine,
) -> None:
    # Given existing automatic selection policy and a valid held-symbol stop.
    protected_engine.trading_settings = TradingSettings(auto_symbol_selection_enabled=True)

    # When selection fails, characterize the current fail-closed policy.
    with patch(
        "nasdaq_auto_trader.engine_automatic_cycle.prepare_production_automatic_selection",
        side_effect=OSError("selector unavailable"),
    ), pytest.raises(PreOrderCycleError) as failure:
        protected_engine.run_once()

    # Then no implied authorization is invented to get around selection failure.
    assert failure.value.reason == "market_data_unavailable"


def test_sell_count_cap_still_blocks_protective_order() -> None:
    # Given a fully used configured daily sell allowance.
    state = TradingSessionState(sell_count=1)

    # When the same final settings guard evaluates a hard-stop sell.
    result = validate_order_against_settings(
        OrderRequest("HELD", "sell", qty=1),
        AccountSnapshot(100, 194, 100),
        Position("HELD", 1, 94, 100),
        TradingSettings(max_daily_sell_count=1),
        state,
        AUTO_TEST_NOW,
        "dry_run",
    )

    # Then changing buy-sizing dependency cannot silently bypass sell policy.
    assert result is not None
    assert result["reason"] == "max_daily_sell_count_reached"


def test_daily_loss_stops_new_buy_but_allows_existing_protective_sell() -> None:
    # Given a breached account loss cap, separate from a position stop.
    state = TradingSessionState(daily_loss_breached=True)
    settings = TradingSettings()
    account = AccountSnapshot(100, 194, 100)

    # When buy and sell requests enter the same final settings guard.
    buy = validate_order_against_settings(
        OrderRequest("NEW", "buy", qty=1), account, None,
        settings, state, AUTO_TEST_NOW, "dry_run",
    )
    sell = validate_order_against_settings(
        OrderRequest("HELD", "sell", qty=1), account,
        Position("HELD", 1, 94, 100), settings, state, AUTO_TEST_NOW, "dry_run",
    )

    # Then new exposure is blocked while existing exposure can be reduced.
    assert buy is not None and buy["reason"] == "max_daily_loss_reached"
    assert sell is None


def test_final_sell_refresh_does_not_query_buying_power(
    protected_engine: TradingEngine,
) -> None:
    # Given no pending order and an actually observed held quantity.
    # When the automatic final refresh rechecks the sell quantity.
    result = automatic_pending_order_block(
        protected_engine, OrderRequest("HELD", "sell", qty=1), 94,
    )

    # Then the normal refresh path exits before the unavailable buy-only endpoint.
    assert result == PendingOrderCheck(initial_position_qty=1)


def test_pending_sell_order_remains_blocked(
    protected_engine: TradingEngine,
) -> None:
    # Given an existing outstanding order for the held symbol.
    protected_engine.broker = _NeverSubmitBroker((OrderRequest("HELD", "sell", qty=1),))

    # When a second protective order reaches final broker-state reconciliation.
    result = automatic_pending_order_block(
        protected_engine, OrderRequest("HELD", "sell", qty=1), 94,
    )

    # Then duplicate protection remains in force.
    assert result == AutomaticOrderBlock("automatic_symbol_open_order_pending")


@pytest.mark.parametrize("status", [ClaimStatus.SUBMITTED, ClaimStatus.UNCERTAIN])
def test_duplicate_sell_signal_remains_blocked_after_restart(
    tmp_path: Path, status: ClaimStatus,
) -> None:
    # Given a durable sell signal whose previous outcome must not be replayed.
    path = tmp_path / "session.json"
    store = TradingSessionStore(path)
    key = SignalKey("2026-07-13", "audit", "1", "HELD", "sell", "2026-07-13T14:30:00Z")
    request = SafetyReservationRequest(
        market_date="2026-07-13", side="sell", timestamp=AUTO_TEST_NOW.isoformat(),
        max_daily_buy_count=0, max_daily_sell_count=0, cooldown_minutes=0,
        daily_loss_breached=False, daily_loss_state_unavailable=False,
        baseline_available=True,
    )
    assert store.claim_and_reserve_safety(key, request).granted
    store.complete(key, status)

    # When a restarted process attempts the same sell signal.
    result = TradingSessionStore(path).claim_and_reserve_safety(key, request)

    # Then the recorded signal is rejected even with unlimited sell count.
    assert not result.granted
    assert result.reason == f"signal_key_{status.value}"
