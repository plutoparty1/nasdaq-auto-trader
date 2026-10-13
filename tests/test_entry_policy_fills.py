from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from nasdaq_auto_trader.backtest import Backtester
from nasdaq_auto_trader.backtest_costs import BacktestCosts
from nasdaq_auto_trader.daily_buy_objective import daily_minimum_decision
from nasdaq_auto_trader.entry_policy_experiment import EntryPolicyStrategy
from nasdaq_auto_trader.models import (
    AccountSnapshot,
    OrderRequest,
    Position,
    TradeDecision,
)
from tests.test_entry_policy_strategy import history, shared_config


@dataclass(frozen=True, slots=True)
class UntouchedLimitRisk:
    strategy: EntryPolicyStrategy

    def build_order(self, decision: TradeDecision, account: AccountSnapshot,
                    position: Position | None, latest_price: float) -> OrderRequest | None:
        if decision.action != "buy":
            return None
        timestamp = self.strategy.records[-1].evaluation_timestamp
        self.strategy.register_order_accepted(decision.symbol, timestamp)
        return OrderRequest(decision.symbol, "buy", type="limit", qty=1, limit_price=1)


def test_unfilled_orders_never_become_positions_or_realized_pnl() -> None:
    strategy = EntryPolicyStrategy(shared_config(), "A")
    result = Backtester(strategy, UntouchedLimitRisk(strategy),
                        costs=BacktestCosts(quantity_step=1), fill_observer=strategy).run(
                            {"TEST": history(falling=True)}, starting_cash=1000)
    assert result.trades == ()
    assert result.ending_positions == ()
    assert result.ending_value == result.starting_cash
    assert {item.reason for item in result.rejections} == {
        "limit_not_touched_expired", "end_of_data_unfilled",
    }
    assert strategy.filled_buy_sessions == frozenset()
    assert sum(item.forced for item in strategy.records) > 1


def test_partial_fill_and_duplicate_notification_do_not_complete_one_share_early() -> None:
    strategy = EntryPolicyStrategy(shared_config(), "A")
    timestamp = history()[-1].timestamp
    strategy.register_entry_fill("TEST", 100, .5, timestamp)
    strategy.register_entry_fill("TEST", 100, .5, timestamp)
    assert strategy.filled_buy_sessions == frozenset()
    strategy.register_entry_fill("TEST", 100, 1, timestamp)
    assert strategy.filled_buy_sessions == frozenset({"2025-08-08"})


@pytest.mark.parametrize("due,held,short", [(True, False, False), (False, False, False),
                                         (True, True, False), (True, False, True)])
def test_offline_minimum_promotion_matches_actual_source_helper(
    due: bool, held: bool, short: bool,
) -> None:
    strategy = EntryPolicyStrategy(shared_config(), "A")
    data = history(falling=True)
    if short:
        data = data[:5]
    position = Position("TEST", 1, data[-1].close, data[-1].close) if held else None
    decision = TradeDecision("TEST", "hold", 0, data[-1].close, ["below_long_regime"])
    actual = daily_minimum_decision(strategy, decision, data, position, due=due)
    proxy = strategy._minimum_proxy(decision, data, position, due=due)
    assert proxy == actual


def test_risk_sizing_floor_preserves_max_legacy_distance_for_all_policies() -> None:
    data = history()
    floors = []
    for policy in ("A", "B", "C"):
        strategy = EntryPolicyStrategy(replace(shared_config(), sell_score=99), policy)
        decision = strategy.decide("TEST", data, None)
        floors.append(strategy.initial_stop_for("TEST", decision.latest_price))
    assert floors[0] == floors[1] == floors[2]
    assert floors[0] == pytest.approx(data[-1].close * .97)
