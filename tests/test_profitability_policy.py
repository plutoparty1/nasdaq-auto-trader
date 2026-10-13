from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from nasdaq_auto_trader.experimental_exit_models import ExitPolicy
from nasdaq_auto_trader.models import Bar, OrderRequest, Position
from nasdaq_auto_trader.strategy_config import StrategyConfig


def history(*, spread: float = 0.02, falling: bool = False) -> list[Bar]:
    start = datetime(2026, 1, 2, 21, tzinfo=UTC)
    prices = [10 + (69 - index if falling else index) * 0.001 for index in range(70)]
    return [Bar("TEST", (start + timedelta(days=index)).isoformat(), price,
                price + spread, price - spread, price, 1000 + index)
            for index, price in enumerate(prices)]


def config() -> StrategyConfig:
    return StrategyConfig(sma_fast=5, sma_slow=20, ema_fast=5, ema_slow=20,
                          long_sma=20, stop_loss_pct=0.03, take_profit_pct=0.05,
                          sell_score=99)


def test_c_sizes_from_first_initial_stop_while_original_proxy_stays_wider() -> None:
    # Given ATR distance exceeds the C fixed stop distance.
    from nasdaq_auto_trader.entry_policy_experiment import EntryPolicyStrategy
    from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy

    bars = history(spread=0.5)
    original = EntryPolicyStrategy(config(), "C").decide("TEST", bars, None)
    strategy = ProfitabilityStrategy(config(), None)
    # When the new offline strategy evaluates the same entry.
    result = strategy.decide("TEST", bars, None)
    # Then only its sizing floor uses the first stop; the prior comparator is intact.
    assert result.risk_per_share == pytest.approx(result.latest_price * 0.03)
    assert original.risk_per_share == pytest.approx(3)
    assert strategy.initial_stop_for("TEST", 10.5) == pytest.approx(10.5 * 0.97)


@pytest.mark.parametrize("policy", [None, ExitPolicy(), ExitPolicy(fixed_stop_pct=0.10)])
def test_every_policy_keeps_c_conflict_and_duplicate_gates(policy: ExitPolicy | None) -> None:
    # Given thresholds at which both actual indicator scores qualify.
    from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy

    strategy = ProfitabilityStrategy(replace(config(), buy_score=1, sell_score=1), policy)
    bars = history()
    # When the same completed bar is evaluated twice.
    first = strategy.decide("TEST", bars, None)
    second = strategy.decide("TEST", bars, None)
    # Then conflict and duplicate guards both remain available in every exit policy.
    assert first.action == second.action == "hold"
    assert "conflicting_entry_exit_signal" in first.reasons
    assert "completed_bar_already_evaluated" in second.reasons


@pytest.mark.parametrize("spread", [0.0001, 1.0, float("nan")])
def test_entry_atr_rejects_invalid_or_outside_bounds(spread: float) -> None:
    # Given a qualifying signal but invalid, too narrow, or too wide entry ATR.
    from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy

    strategy = ProfitabilityStrategy(config(), ExitPolicy(stop_mode="entry_atr"))
    # When evaluating the candidate.
    result = strategy.decide("TEST", history(spread=spread), None)
    # Then it cannot submit an entry or invent a fallback stop.
    assert result.action == "hold"
    assert result.reasons[-1] in {"invalid_entry_atr", "entry_stop_outside_bounds"}
    assert strategy.initial_stop_for("TEST", result.latest_price) is None


def test_entry_atr_stays_anchored_to_signal_volatility_after_fill() -> None:
    # Given entry ATR equals 0.04 and the fill price changes.
    from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy

    strategy = ProfitabilityStrategy(config(), ExitPolicy(stop_mode="entry_atr"))
    bars = history()
    strategy.decide("TEST", bars, None)
    strategy.register_entry_fill("TEST", 10.1, 1, bars[-1].timestamp)
    # When subsequent daily volatility grows sharply.
    held = Position("TEST", 1, 10.0, 10.1)
    strategy.decide("TEST", history(spread=0.3), held)
    # Then the initial ATR stop retains its entry value.
    assert strategy.initial_stop_for("TEST", 10.1) == pytest.approx(9.98)


def test_wide_stop_keeps_general_technical_exit_enabled() -> None:
    # Given a held position above its wide protective stop and a declining trend.
    from nasdaq_auto_trader.profitability_strategy import ProfitabilityStrategy

    strategy = ProfitabilityStrategy(replace(config(), sell_score=4), ExitPolicy())
    bars = history(falling=True)
    strategy.register_entry_fill("TEST", 10.01, 1, bars[0].timestamp)
    # When the completed daily technical sell qualifies.
    result = strategy.decide("TEST", bars, Position("TEST", 1, 10, 10.01))
    # Then the general sell can precede the 8% stop.
    assert result.action == "sell"
    assert result.score < 88


@pytest.mark.parametrize("opening,volume", [(10.1, 1000), (9.99, 1000), (9.9, 0)])
def test_limit_touch_without_admissible_open_does_not_fill(opening: float, volume: float) -> None:
    # Given a buy limit touched later but without an admissible cost-inclusive open.
    from nasdaq_auto_trader.profitability_execution import ConservativeCosts

    costs = ConservativeCosts(spread_bps=10, slippage_bps=10, quantity_step=1)
    order = OrderRequest("TEST", "buy", type="limit", qty=1, limit_price=10)
    bar = Bar("TEST", "2026-04-01T20:00:00+00:00", opening, 10.2, 9.8, 10, volume)
    # When the conservative execution model prices the next bar.
    result = costs.fill_price(order, bar)
    # Then low touching the limit alone is insufficient.
    assert result is None


def test_admissible_open_charges_impact_without_limit_clamping() -> None:
    # Given the next open leaves room for the full execution cost below the limit.
    from nasdaq_auto_trader.profitability_execution import ConservativeCosts

    costs = ConservativeCosts(spread_bps=10, slippage_bps=10, quantity_step=1)
    order = OrderRequest("TEST", "buy", type="limit", qty=1, limit_price=10)
    bar = Bar("TEST", "2026-04-01T20:00:00+00:00", 9.9, 10.2, 9.8, 10, 1000)
    # When the open is priced.
    result = costs.fill_price(order, bar)
    # Then full spread and slippage are charged.
    assert result == pytest.approx((9.91485, 0.01485))
