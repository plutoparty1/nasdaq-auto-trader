from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

import pytest

from nasdaq_auto_trader import daily_buy_objective as objective
from nasdaq_auto_trader.config_settings import TradingSessionState, TradingSettings
from nasdaq_auto_trader.config_validation import validate_settings
from nasdaq_auto_trader.models import Bar, Position, TradeDecision
from nasdaq_auto_trader.strategy import TechnicalStrategy
from nasdaq_auto_trader.strategy_config import StrategyConfig

NOW = datetime(2026, 9, 22, 0, 30, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class History:
    order_id: str = "order-1"
    symbol: str = "AAPL"
    side: str = "buy"
    quantity: float = 1
    filled_quantity: float = 1
    average_fill_price: float = 100
    status: str = "filled"
    submitted_at: datetime | None = NOW - timedelta(hours=1)
    is_original_order: bool = True
    requested_quantity_known: bool = True


def settings(*, dry_run: bool = False) -> TradingSettings:
    return replace(
        TradingSettings(), daily_minimum_buy_enabled=True,
        auto_symbol_selection_enabled=True, dry_run=dry_run,
    )


@pytest.mark.parametrize("automatic,quantity", [(False, 1), (True, 2)])
def test_daily_minimum_requires_automatic_single_share_orders(
    automatic: bool, quantity: int,
) -> None:
    # Given
    configured = replace(
        settings(), auto_symbol_selection_enabled=automatic,
        order_qty=quantity, max_position_qty=quantity,
    )
    # When
    result = validate_settings(configured)
    # Then
    assert any("daily_minimum_buy_enabled" in error for error in result.errors)


def test_daily_minimum_is_disabled_by_default() -> None:
    # Given / When / Then
    assert TradingSettings().daily_minimum_buy_enabled is False


@pytest.mark.parametrize("history", [(), (History(filled_quantity=0, status="canceled"),)])
def test_due_when_no_confirmed_fill_even_after_submission_count(history: tuple[History, ...]) -> None:
    # Given
    state = TradingSessionState(market_date="2026-09-21", buy_count=5)
    # When
    result = objective.daily_buy_due(settings(), state, NOW, history)
    # Then
    assert result.due


def test_current_eastern_day_fill_satisfies_objective() -> None:
    # Given
    history = (History(),)
    # When
    result = objective.daily_buy_due(settings(), TradingSessionState(), NOW, history)
    # Then
    assert not result.due
    assert result.reason == "daily_minimum_buy_filled"


@pytest.mark.parametrize("row", [
    History(submitted_at=NOW - timedelta(days=1)),
    History(side="sell"),
    History(is_original_order=False),
])
def test_previous_day_sells_and_request_rows_do_not_satisfy_objective(row: History) -> None:
    # Given / When
    result = objective.daily_buy_due(settings(), TradingSessionState(), NOW, (row,))
    # Then
    assert result.due


@pytest.mark.parametrize("row", [
    History(filled_quantity=0, status="new"),
    History(filled_quantity=0.5, status="partially_filled"),
    History(filled_quantity=float("nan")),
    History(filled_quantity=2),
    History(submitted_at=None),
    History(submitted_at=NOW.replace(tzinfo=None)),
    History(submitted_at=NOW + timedelta(minutes=1)),
    History(order_id=""),
    History(status="filled", filled_quantity=0),
    History(status="unknown", filled_quantity=0),
    History(requested_quantity_known=False, status="partially_filled"),
])
def test_unresolved_or_invalid_history_fails_closed(row: History) -> None:
    # Given / When
    result = objective.daily_buy_due(settings(), TradingSessionState(), NOW, (row,))
    # Then
    assert not result.due
    assert result.reason in {
        "daily_minimum_history_unresolved", "daily_minimum_history_invalid",
    }


def test_missing_history_fails_closed() -> None:
    # Given / When
    result = objective.daily_buy_due(settings(), TradingSessionState(), NOW)
    # Then
    assert not result.due
    assert result.reason == "daily_minimum_history_unavailable"


def test_duplicate_partial_fills_are_not_double_counted() -> None:
    # Given
    row = History(filled_quantity=0.5, status="canceled")
    # When
    result = objective.daily_buy_due(settings(), TradingSessionState(), NOW, (row, row))
    # Then
    assert result.due


def test_conflicting_duplicate_identity_fails_closed() -> None:
    # Given
    rows = (History(), History(symbol="MSFT"))
    # When
    result = objective.daily_buy_due(settings(), TradingSessionState(), NOW, rows)
    # Then
    assert not result.due
    assert result.reason == "daily_minimum_history_invalid"


@pytest.mark.parametrize("market_date,due", [("2026-09-21", False), ("2026-09-20", True)])
def test_dry_run_counters_are_explicitly_simulated(market_date: str, due: bool) -> None:
    # Given
    state = TradingSessionState(market_date=market_date, buy_count=1)
    # When
    result = objective.daily_buy_due(settings(dry_run=True), state, NOW)
    # Then
    assert result.due is due
    assert "simulat" in result.reason


def bars() -> list[Bar]:
    return [Bar("AAPL", f"2026-09-{index:02}", 100, 102, 98, 100, 1000) for index in range(1, 221)]


def test_minimum_objective_preserves_rejected_signal_and_cannot_create_buy() -> None:
    # Given
    strategy = TechnicalStrategy(StrategyConfig(buy_score=99))
    samples = bars()
    decision = strategy.decide("AAPL", samples, None)
    # When
    result = objective.daily_minimum_decision(strategy, decision, samples, None, due=True)
    # Then
    assert result.action == "hold"
    assert result is decision
    assert result.score < strategy.config.buy_score
    assert result.reasons == decision.reasons
    assert "daily_minimum_best_affordable" not in result.reasons
    assert result.risk_per_share == decision.risk_per_share
    assert decision.action == "hold"


@pytest.mark.parametrize("case", ["not_due", "held", "short", "no_data", "sell", "buy"])
def test_promotion_preserves_noneligible_decisions(case: str) -> None:
    # Given
    strategy = TechnicalStrategy()
    samples = bars() if case != "short" else bars()[:5]
    if case == "no_data":
        samples = []
    action = "sell" if case == "sell" else "buy" if case == "buy" else "hold"
    decision = TradeDecision("AAPL", action, 2, 100, ["no_signal"])
    position = Position("AAPL", 1, 100, 100) if case == "held" else None
    # When
    result = objective.daily_minimum_decision(
        strategy, decision, samples, position, due=case != "not_due",
    )
    # Then
    assert result is decision
