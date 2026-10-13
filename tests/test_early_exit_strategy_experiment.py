from dataclasses import replace

import pytest

from nasdaq_auto_trader.experimental_exit import ExitPolicy, ExperimentalExitStrategy
from nasdaq_auto_trader.models import Bar, Position, TradeDecision
from nasdaq_auto_trader.strategy_config import StrategyConfig


def history(price: float = 10, spread: float = .01, timestamp: str = "2026-01-15") -> list[Bar]:
    return [Bar("TEST", "2026-01-01", price, price + spread, price - spread, price, 100)] * 14 + [
        Bar("TEST", timestamp, price, price + spread, price - spread, price, 100)
    ]


class BothSignals(ExperimentalExitStrategy):
    def _minimum_bars(self) -> int:
        return 1

    def _buy_score(self, closes: list[float], bars: list[Bar], latest_price: float) -> tuple[int, list[str]]:
        return 6, ["buy_fixture"]

    def _sell_score(self, closes: list[float], bars: list[Bar], latest_price: float) -> tuple[int, list[str]]:
        return 6, ["sell_fixture"]


def test_fixed_mode_disables_nearby_atr_exit() -> None:
    strategy = BothSignals(StrategyConfig(sell_score=99), ExitPolicy())
    decision = strategy.decide("TEST", history(), Position("TEST", 1, 9.93, 10))
    assert decision.action == "hold"
    assert strategy.diagnostics["TEST"].effective_stop_price == pytest.approx(9.2)


def test_entry_atr_locks_to_fill_and_does_not_recalculate() -> None:
    strategy = BothSignals(StrategyConfig(sell_score=99), ExitPolicy(stop_mode="entry_atr"))
    entry_decision = strategy.decide("TEST", history(), None)
    assert entry_decision.risk_per_share == pytest.approx(.06)
    strategy.register_entry_fill("TEST", 10.1, 1, "2026-01-16T14:30:00+00:00")
    decision = strategy.decide("TEST", history(10.1, .5, "2026-01-16"), Position("TEST", 1, 10.03, 10.1))
    assert decision.reasons == ["atr_stop_loss"]
    assert strategy.diagnostics["TEST"].initial_stop_price == pytest.approx(10.04)


@pytest.mark.parametrize("spread", [0, float("nan"), float("inf")])

def test_invalid_entry_atr_blocks_new_entry(spread: float) -> None:
    strategy = BothSignals(StrategyConfig(), ExitPolicy(stop_mode="entry_atr"))
    decision = strategy.decide("TEST", history(spread=spread), None)
    assert decision.action == "hold" and decision.reasons == ["invalid_entry_atr"]


def test_missing_entry_atr_does_not_disable_valid_fixed_take_profit() -> None:
    strategy = BothSignals(StrategyConfig(), ExitPolicy(stop_mode="entry_atr"))
    decision = strategy.decide("TEST", history(12), Position("TEST", 1, 12, 10))
    assert decision.reasons == ["fixed_take_profit"]


def test_conflicting_entry_is_opt_in_and_suppressed_before_buy() -> None:
    strategy = BothSignals(StrategyConfig(), ExitPolicy(block_conflicting_entry=True))
    decision = strategy.decide("TEST", history(), None)
    assert decision.action == "hold" and decision.reasons == ["conflicting_entry_exit_signal"]


def test_same_bar_general_sell_is_gated_but_hard_stop_is_not() -> None:
    strategy = BothSignals(StrategyConfig(), ExitPolicy(completed_bar_only_general=True))
    strategy.decide("TEST", history(), None)
    strategy.register_entry_fill("TEST", 10, 1, "2026-01-15T15:00:00+00:00")
    held = strategy.decide("TEST", history(), Position("TEST", 1, 10, 10))
    stopped = strategy.decide("TEST", history(), Position("TEST", 1, 9.1, 10))
    assert held.action == "hold" and held.reasons == ["same_completed_bar"]
    assert stopped.reasons == ["fixed_stop_loss"]


def test_new_bar_general_sell_releases_gate() -> None:
    strategy = BothSignals(StrategyConfig(), ExitPolicy(completed_bar_only_general=True))
    strategy.decide("TEST", history(), None)
    strategy.register_entry_fill("TEST", 10, 1, "2026-01-15T15:00:00+00:00")
    decision = strategy.decide("TEST", history(timestamp="2026-01-16"), Position("TEST", 1, 10, 10))
    assert decision.action == "sell" and decision.reasons == ["sell_fixture"]


def test_trailing_restarts_and_remains_latched_through_crash() -> None:
    policy = ExitPolicy(trailing_activation_pct=.02, trailing_drawdown_pct=.01)
    strategy = BothSignals(StrategyConfig(sell_score=99), policy)
    strategy.register_entry_fill("TEST", 100, 2, "2026-01-15T15:00:00+00:00")
    strategy.decide("TEST", history(102), Position("TEST", 2, 204, 100))
    restarted = BothSignals(StrategyConfig(sell_score=99), policy)
    restarted.load_state(strategy.export_state())
    partial = restarted.decide("TEST", history(100.98), Position("TEST", 1, 100.98, 100))
    crashed = restarted.decide("TEST", history(99), Position("TEST", 1, 99, 100))
    assert partial.reasons == ["trailing_profit_protection"]
    assert crashed.reasons == ["trailing_profit_protection"]


def test_reentry_does_not_inherit_previous_high_water() -> None:
    strategy = BothSignals(StrategyConfig(sell_score=99), ExitPolicy())
    strategy.register_entry_fill("TEST", 100, 1, "2026-01-15T15:00:00+00:00")
    strategy.decide("TEST", history(110), Position("TEST", 1, 110, 100))
    strategy.register_exit_fill("TEST", 0)
    strategy.register_entry_fill("TEST", 90, 1, "2026-01-16T15:00:00+00:00")
    decision = strategy.decide("TEST", history(90), Position("TEST", 1, 90, 90, 110))
    assert decision.action == "hold"
    assert strategy.diagnostics["TEST"].high_water_price == 90


def test_additional_buy_preserves_absolute_initial_stop() -> None:
    strategy = BothSignals(StrategyConfig(sell_score=99), ExitPolicy())
    strategy.register_entry_fill("TEST", 100, 1, "2026-01-15T15:00:00+00:00")
    strategy.register_entry_fill("TEST", 96, 2, "2026-01-16T15:00:00+00:00")
    strategy.decide("TEST", history(96), Position("TEST", 2, 192, 96))
    assert strategy.diagnostics["TEST"].initial_stop_price == pytest.approx(92)


def test_state_from_other_policy_is_rejected() -> None:
    strategy = BothSignals(StrategyConfig(), ExitPolicy())
    other = BothSignals(StrategyConfig(), replace(ExitPolicy(), fixed_stop_pct=.10))
    with pytest.raises(ValueError, match="fingerprint"):
        other.load_state(strategy.export_state())


def test_real_indicators_reproduce_buy_sell_rebuy_on_same_bar() -> None:
    from nasdaq_auto_trader.strategy import TechnicalStrategy

    closes = [100 + index * .1 for index in range(220)]
    closes[-1] += 1
    data = [Bar("TEST", f"bar-{index}", price, price + .01, price - .01, price, 100 + index)
            for index, price in enumerate(closes)]
    legacy = TechnicalStrategy()
    bought = legacy.decide("TEST", data, None)
    sold = legacy.decide("TEST", data, Position("TEST", 1, closes[-1], closes[-1]))
    rebought = legacy.decide("TEST", data, None)
    assert (bought.action, sold.action, rebought.action) == ("buy", "sell", "buy")
    assert (bought.score, sold.score) == (10, 4)
    blocked = ExperimentalExitStrategy(StrategyConfig(), ExitPolicy(block_conflicting_entry=True)).decide("TEST", data, None)
    assert blocked.action == "hold" and blocked.reasons == ["conflicting_entry_exit_signal"]


def test_entry_atr_missing_history_and_inverted_range_block_buy() -> None:
    strategy = BothSignals(StrategyConfig(), ExitPolicy(stop_mode="entry_atr"))
    for data in (history()[:1], history(spread=-.01)):
        decision = strategy.decide("TEST", data, None)
        assert decision.action == "hold" and decision.reasons == ["invalid_entry_atr"]


def test_minimum_hold_never_blocks_activated_trailing() -> None:
    policy = ExitPolicy(trailing_activation_pct=.02, trailing_drawdown_pct=.01,
                        minimum_general_hold_minutes=60)
    strategy = BothSignals(StrategyConfig(), policy)
    strategy.register_entry_fill("TEST", 100, 1, "2026-01-15T15:00:00+00:00")
    strategy.decide("TEST", history(102, timestamp="2026-01-15T15:01:00+00:00"), Position("TEST", 1, 102, 100))
    decision = strategy.decide("TEST", history(100.98, timestamp="2026-01-15T15:02:00+00:00"), Position("TEST", 1, 100.98, 100))
    assert decision.reasons == ["trailing_profit_protection"]


def test_initial_stop_rechecks_atr_bounds_at_fill_price() -> None:
    strategy = BothSignals(StrategyConfig(), ExitPolicy(stop_mode="entry_atr"))
    strategy.decide("TEST", history(), None)
    assert strategy.initial_stop_for("TEST", 10) == pytest.approx(9.94)
    assert strategy.initial_stop_for("TEST", 100) is None


def test_emergency_stop_has_explicit_effective_price_and_risk() -> None:
    strategy = BothSignals(StrategyConfig(sell_score=99), ExitPolicy(emergency_stop_pct=.05))
    buy = strategy.decide("TEST", history(), None)
    assert buy.risk_per_share == pytest.approx(.5)
    strategy.register_entry_fill("TEST", 10, 1, "2026-01-16")
    sold = strategy.decide("TEST", history(), Position("TEST", 1, 9.4, 10))
    assert sold.reasons == ["emergency_fixed_stop_loss"]
    assert strategy.diagnostics["TEST"].effective_stop_price == pytest.approx(9.5)


def test_legacy_sizing_remains_conservative_but_explicit_policy_uses_effective_stop() -> None:
    from nasdaq_auto_trader.strategy import TechnicalStrategy

    config = StrategyConfig(stop_loss_pct=.05)
    old = TechnicalStrategy(config)._risk_per_share(history(), 10)
    chosen = BothSignals(config, ExitPolicy(stop_mode="legacy")).decide("TEST", history(), None)
    assert old == pytest.approx(.5)
    assert chosen.risk_per_share == pytest.approx(.06)


def test_nonfinite_persisted_state_is_rejected_atomically() -> None:
    import json

    strategy = BothSignals(StrategyConfig(), ExitPolicy())
    strategy.register_entry_fill("TEST", 10, 1, "2026-01-16")
    old = strategy.export_state()
    corrupted = json.loads(old)
    corrupted["positions"][0]["high_water_price"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        strategy.load_state(json.dumps(corrupted))
    assert strategy.export_state() == old


class AdditionalEntryFixture(ExperimentalExitStrategy):
    def decide(self, symbol: str, bars: list[Bar], position: Position | None) -> TradeDecision:
        if len(bars) <= 2:
            price = bars[-1].close
            return TradeDecision(symbol, "buy", 10, price, ["additional_entry_fixture"],
                                 self._risk_per_share(bars, price))
        return super().decide(symbol, bars, position)


def test_actual_backtester_rejects_additional_fill_using_retained_stop() -> None:
    from nasdaq_auto_trader.backtest import BacktestCosts, Backtester
    from nasdaq_auto_trader.risk import RiskConfig, RiskManager

    strategy = AdditionalEntryFixture(StrategyConfig(sell_score=99), ExitPolicy())
    data = [Bar("TEST", "2026-01-01", 100, 100, 100, 100, 100),
            Bar("TEST", "2026-01-02", 100, 110, 100, 110, 100),
            Bar("TEST", "2026-01-03", 110, 110, 110, 110, 100)]
    risk = RiskManager(RiskConfig(order_qty=1, max_position_pct=1, min_cash_buffer_pct=0,
                                  risk_per_trade_pct=0, allow_additional_buy=True))
    result = Backtester(strategy, risk, costs=BacktestCosts(quantity_step=1),
                        max_trade_risk_pct=.012, max_portfolio_risk_pct=.02,
                        fill_observer=strategy).run({"TEST": data}, 1000)
    assert len(result.trades) == 1
    assert result.ending_positions[0].qty == 1
    assert result.rejections[-1].reason == "portfolio_risk_limit_at_fill"
    assert strategy.initial_stop_for("TEST", 110) == pytest.approx(92)


def test_actual_backtester_preserves_emergency_stop_after_average_down() -> None:
    from nasdaq_auto_trader.backtest import BacktestCosts, Backtester
    from nasdaq_auto_trader.risk import RiskConfig, RiskManager

    strategy = AdditionalEntryFixture(StrategyConfig(sell_score=99), ExitPolicy(emergency_stop_pct=.05))
    data = [Bar("TEST", "2026-01-01", 100, 100, 100, 100, 100),
            Bar("TEST", "2026-01-02", 100, 100, 98, 98, 100),
            Bar("TEST", "2026-01-03", 98, 98, 94.5, 94.5, 100),
            Bar("TEST", "2026-01-04", 94.5, 94.5, 94.5, 94.5, 100)]
    risk = RiskManager(RiskConfig(order_qty=1, max_position_pct=1, min_cash_buffer_pct=0,
                                  risk_per_trade_pct=0, allow_additional_buy=True))
    result = Backtester(strategy, risk, costs=BacktestCosts(quantity_step=1),
                        fill_observer=strategy).run({"TEST": data}, 1000)
    assert [trade.side for trade in result.trades] == ["buy", "buy", "sell"]
    assert result.trades[-1].reasons == ("emergency_fixed_stop_loss",)
    assert result.trades[-1].price == pytest.approx(94.5)
    assert result.trades[-1].qty == 1
    assert result.trades[-1].gross_pnl == pytest.approx(-4.5)
    assert result.ending_positions[0].qty == 1
    restarted = AdditionalEntryFixture(StrategyConfig(sell_score=99), ExitPolicy(emergency_stop_pct=.05))
    restarted.load_state(strategy.export_state())
    assert restarted.initial_stop_for("TEST", 99) == pytest.approx(95)


def test_legacy_policy_rejects_unsupported_emergency_stop() -> None:
    with pytest.raises(ValueError, match="legacy.*emergency"):
        ExitPolicy(stop_mode="legacy", emergency_stop_pct=.01)
