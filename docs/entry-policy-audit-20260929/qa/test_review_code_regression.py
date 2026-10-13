from dataclasses import replace

from nasdaq_auto_trader.backtest_costs import BacktestCosts
from nasdaq_auto_trader.backtest_execution import ExecutionBook
from nasdaq_auto_trader.entry_comparison_risk import MatchedEntryRisk
from nasdaq_auto_trader.entry_policy_experiment import EntryPolicyStrategy
from nasdaq_auto_trader.models import Bar, Position, TradeDecision
from nasdaq_auto_trader.strategy_config import StrategyConfig


def test_pending_entry_cannot_exceed_common_exposure_limit_after_other_holding_gap() -> None:
    # Given: the real comparison risk accepts exactly 50% exposure at submission.
    costs = BacktestCosts(quantity_step=1)
    strategy = EntryPolicyStrategy(StrategyConfig(), "B")
    risk = MatchedEntryRisk(strategy, costs)
    risk.timestamp = "2025-01-02T21:00:00+00:00"
    book = ExecutionBook(40, costs, max_trade_risk_pct=.01, risk_includes_costs=True,
                         max_total_position_pct=.5)
    book.positions["HELD"] = Position("HELD", 1, 20, 20)
    decision = TradeDecision("NEW", "buy", 5, 10, [], .3)
    order = risk.build_order(decision, book.account(available=True), None, 10)
    assert order is not None
    book.submit(order, decision, risk.timestamp)

    # When: an existing holding gaps up before the next-bar entry can fill.
    book.positions["HELD"] = replace(book.positions["HELD"], market_value=40)
    book.execute(Bar("NEW", "2025-01-03T21:00:00+00:00", 10, 10.1, 9.9, 10, 100))

    # Then: the new entry must be rejected under the common 50% entry cap.
    assert "NEW" not in book.positions
