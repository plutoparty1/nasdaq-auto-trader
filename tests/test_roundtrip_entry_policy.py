from datetime import datetime, timezone

from nasdaq_auto_trader.automatic_entry_eligibility import EntryEligibilityContext
from nasdaq_auto_trader.automatic_risk import AutomaticRiskLimits
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.daily_buy_objective import daily_minimum_decision
from nasdaq_auto_trader.models import AccountSnapshot, Bar, Position
from nasdaq_auto_trader.risk import RiskConfig
from nasdaq_auto_trader.strategy import TechnicalStrategy
from nasdaq_auto_trader.strategy_config import StrategyConfig


def history(*, falling: bool = False) -> list[Bar]:
    prices = [20.61 + (219 - index) * (.01 if falling else -.01)
              for index in range(220)]
    return [Bar("CMCSA", "2026-10-12T20:00:00+00:00", price,
                price + .01, price - .01, price, 1000 + index)
            for index, price in enumerate(prices)]


def test_minimum_objective_cannot_promote_below_regime_hold() -> None:
    # Given: the observed reason was below_long_regime with buy score zero.
    strategy = TechnicalStrategy()
    bars = history(falling=True)
    decision = strategy.decide("CMCSA", bars, None)
    assert decision.score == 0
    # When: the saved minimum-buy setting requests an entry.
    result = daily_minimum_decision(strategy, decision, bars, None, due=True)
    # Then: the technical rejection remains effective.
    assert result.action == "hold"
    assert "below_long_regime" in result.reasons


def test_entry_rejected_when_same_history_has_qualifying_sell_signal() -> None:
    # Given: rising history also reaches the overextension sell threshold.
    strategy = TechnicalStrategy(StrategyConfig(buy_score=1, sell_score=1))
    bars = history()
    assert strategy._sell_score([bar.close for bar in bars], bars, 20.61)[0] >= 1
    # When: the flat-account entry is evaluated.
    result = strategy.decide("CMCSA", bars, None)
    # Then: a conflicting general exit vetoes entry.
    assert result.action == "hold"
    assert "conflicting_entry_exit_signal" in result.reasons


def test_minimum_objective_cannot_raise_configured_risk_budget() -> None:
    # Given: one share risks $1.6488 against a $1.081456287092 budget.
    config = AppConfig(strategy=StrategyConfig(sell_score=99, stop_loss_pct=.08),
                       risk=RiskConfig(order_qty=1, risk_per_trade_pct=.02, max_position_pct=1))
    context = EntryEligibilityContext(AccountSnapshot(54.0728143546, 54.0728143546,
                                                     54.0728143546), {},
                                      daily_minimum_due=True)
    bars = history()
    assert TechnicalStrategy(config.strategy).decide("CMCSA", bars, None).action == "buy"
    # When: minimum-buy eligibility is evaluated using the configured budget.
    result = context.evaluate(config, {"CMCSA": bars}, AutomaticRiskLimits(1, 1, 1000, 100, .05),
                              datetime(2026, 10, 13, tzinfo=timezone.utc))
    # Then: affordability cannot override the stop-risk budget.
    assert not result.eligible_symbols
    assert "entry_risk_capacity:CMCSA" in result.warnings


def test_protective_exit_remains_available_despite_entry_conflict_policy() -> None:
    # Given: a held share has crossed its configured fixed stop.
    strategy = TechnicalStrategy(StrategyConfig(stop_loss_pct=.08))
    bars = history()
    position = Position("CMCSA", 1, 18, 20.61)
    # When: current position protection is evaluated.
    result = strategy.decide("CMCSA", bars, position)
    # Then: protection still sells regardless of expected profit.
    assert result.action == "sell"
    assert result.reasons == ["fixed_stop_loss"]
