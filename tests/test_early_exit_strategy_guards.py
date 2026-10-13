"""Offline regressions for opt-in corrections; no broker is constructed."""

from dataclasses import replace
from unittest.mock import patch

import pytest

from nasdaq_auto_trader.models import Bar, Position
from nasdaq_auto_trader.strategy import TechnicalStrategy
from nasdaq_auto_trader.strategy_config import StrategyConfig


def bars(price: float = 10, count: int = 15) -> list[Bar]:
    return [Bar("TEST", f"2026-01-{i + 1:02d}", price, price + .01,
                price - .01, price, 1000) for i in range(count)]


def test_legacy_atr_stop_precedes_wider_fixed_stop() -> None:
    # Given a 5% fixed stop and a 0.02 x 3 dollar ATR distance.
    strategy = TechnicalStrategy(StrategyConfig(stop_loss_pct=.05))
    position = Position("TEST", 1, 9.93, 10)
    # When the mark is below 9.94 but above 9.50.
    decision = strategy.protective_exit("TEST", bars(), position)
    # Then the legacy ATR condition sells first.
    assert decision is not None and decision.reasons == ["atr_stop_loss"]


@pytest.mark.parametrize("invalid_atr", [0, -1, float("nan"), float("inf")])
def test_corrected_guard_ignores_invalid_atr(invalid_atr: float) -> None:
    # Given an unchanged entry price and invalid ATR.
    config = replace(StrategyConfig(), corrected_exits=True)
    strategy = TechnicalStrategy(config)
    # When protective rules are evaluated without a valid ATR.
    with patch("nasdaq_auto_trader.strategy.atr", return_value=invalid_atr):
        decision = strategy.protective_exit("TEST", bars(), Position("TEST", 1, 10, 10))
    # Then no zero-distance or inverted ATR stop sells the holding.
    assert decision is None


def test_corrected_trailing_remains_active_below_entry() -> None:
    # Given an activated 2%/1% trailing stop and a gap through entry.
    strategy = TechnicalStrategy(replace(StrategyConfig(), corrected_exits=True))
    position = Position("TEST", 1, 99, 100, high_water_price=102)
    # When the price gaps below entry but remains above the hard stop.
    decision = strategy.protective_exit("TEST", bars(99, 1), position)
    # Then already activated protection remains in force.
    assert decision is not None and decision.reasons == ["trailing_profit_protection"]


@pytest.mark.parametrize("invalid_price", [0, -1, float("nan"), float("inf")])
def test_invalid_market_price_cannot_trigger_a_sell(invalid_price: float) -> None:
    # Given no valid account mark and an invalid last bar price.
    strategy = TechnicalStrategy()
    # When the holding is evaluated.
    decision = strategy.decide("TEST", bars(invalid_price), Position("TEST", 1, 0, 10))
    # Then the strategy refuses to trade on invalid market data.
    assert decision.action == "hold" and "invalid_price" in decision.reasons


def test_default_preserves_existing_trailing_policy() -> None:
    # Given legacy protection whose below-entry trailing behavior is retained.
    strategy = TechnicalStrategy()
    # When no fixed or ATR stop is crossed.
    decision = strategy.protective_exit("TEST", bars(99, 1), Position("TEST", 1, 99, 100, 102))
    # Then a live user's policy has not silently changed.
    assert decision is None
