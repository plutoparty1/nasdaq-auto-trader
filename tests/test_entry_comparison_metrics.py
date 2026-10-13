from __future__ import annotations

from nasdaq_auto_trader.backtest import BacktestResult, BacktestTrade, EquityPoint
from nasdaq_auto_trader.entry_comparison_metrics import entry_outcome
from nasdaq_auto_trader.entry_policy_experiment import EntryPolicyStrategy
from nasdaq_auto_trader.entry_policy_experiment_models import EntryDecisionRecord
from nasdaq_auto_trader.exit_experiment import EvaluationSplit
from nasdaq_auto_trader.exit_experiment_metrics import summarize
from nasdaq_auto_trader.strategy_config import StrategyConfig


def test_outcome_joins_fills_not_submissions_and_counts_next_evaluation() -> None:
    strategy = EntryPolicyStrategy(StrategyConfig(), "A")
    strategy.records = [
        EntryDecisionRecord(
            "TEST",
            "A",
            "2025-01-01T21:00:00+00:00",
            "2025-01-01T21:00:00+00:00",
            "fingerprint",
            0,
            6,
            "hold",
            "buy",
            True,
            False,
            "forced",
            False,
            False,
            False,
            10,
            None,
            0.7,
        ),
        EntryDecisionRecord(
            "TEST",
            "A",
            "2025-01-02T21:00:00+00:00",
            "2025-01-02T21:00:00+00:00",
            "fingerprint",
            0,
            6,
            "sell",
            "sell",
            False,
            False,
            "technical",
            False,
            False,
            False,
            10,
            10,
            None,
        ),
        EntryDecisionRecord(
            "UNFILLED",
            "A",
            "2025-01-01T21:00:00+00:00",
            "2025-01-01T21:00:00+00:00",
            "fingerprint",
            0,
            6,
            "hold",
            "buy",
            True,
            False,
            "forced",
            False,
            False,
            False,
            10,
            None,
            0.7,
        ),
    ]
    result = BacktestResult(
        100,
        99.9,
        (
            BacktestTrade(
                "2025-01-01T21:00:00+00:00",
                "2025-01-02T21:00:00+00:00",
                "TEST",
                "buy",
                10,
                1,
                10,
                ("forced",),
                fee=0.05,
            ),
            BacktestTrade(
                "2025-01-02T21:00:00+00:00",
                "2025-01-03T21:00:00+00:00",
                "TEST",
                "sell",
                10,
                1,
                10,
                ("sma_downtrend",),
                pnl=-0.1,
                fee=0.05,
            ),
        ),
        (EquityPoint("2025-01-03T21:00:00+00:00", 99.9, 99.9, 0),),
    )
    performance = summarize(result, fx_rate=1400, operations_monthly_krw=None)
    outcome = entry_outcome(
        result,
        strategy,
        performance,
        EvaluationSplit(
            "final", "2025-01-01T21:00:00+00:00", "2025-01-03T21:00:00+00:00"
        ),
    )
    assert outcome.entries_without_entry_condition == 1
    assert outcome.forced_entry_fills == 1
    assert outcome.next_evaluation_general_exit_fills == 1
    assert outcome.realized_pnl_usd == -0.1
    assert outcome.complete_calendar_months == 0
    assert outcome.literal_five_minute_exits is None


def test_marked_account_loss_remains_visible_without_any_sell() -> None:
    strategy = EntryPolicyStrategy(StrategyConfig(), "C")
    result = BacktestResult(
        100,
        90,
        (
            BacktestTrade(
                "2025-01-01T21:00:00+00:00",
                "2025-01-02T21:00:00+00:00",
                "TEST",
                "buy",
                20,
                1,
                20,
                (),
                fee=0.1,
            ),
        ),
        (EquityPoint("2025-01-03T21:00:00+00:00", 90, 79.9, 10.1),),
    )
    performance = summarize(result, fx_rate=1400, operations_monthly_krw=None)
    outcome = entry_outcome(
        result,
        strategy,
        performance,
        EvaluationSplit(
            "final", "2025-01-01T21:00:00+00:00", "2025-01-03T21:00:00+00:00"
        ),
    )
    assert outcome.realized_pnl_usd == 0
    assert outcome.unrealized_pnl_after_entry_cost_usd == -10
    assert performance.summary.cumulative_return_pct == -10
