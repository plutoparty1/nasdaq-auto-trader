from __future__ import annotations

import calendar
from dataclasses import asdict, dataclass

from .backtest_types import BacktestResult
from .entry_policy_experiment import EntryPolicyStrategy
from .exit_experiment import EvaluationSplit
from .exit_experiment_metrics import Performance


@dataclass(frozen=True, slots=True)
class EntryOutcome:
    entries_without_entry_condition: int
    entries_with_sell_signal: int
    forced_entry_fills: int
    next_evaluation_general_exit_fills: int
    literal_five_minute_exits: None
    realized_pnl_usd: float
    unrealized_pnl_after_entry_cost_usd: float
    complete_calendar_months: int
    target_complete_calendar_months: int
    monthly_evidence_status: str


def entry_outcome(
    result: BacktestResult,
    strategy: EntryPolicyStrategy,
    performance: Performance,
    split: EvaluationSplit,
) -> EntryOutcome:
    records = {
        (record.symbol, record.evaluation_timestamp): record
        for record in strategy.records
    }
    buys = [fill for fill in result.trades if fill.side == "buy"]
    without_condition = conflicts = forced = next_general = 0
    protected = {
        "fixed_stop_loss",
        "atr_stop_loss",
        "fixed_take_profit",
        "atr_take_profit",
        "trailing_profit_protection",
        "time_based_sell",
        "market_close",
    }
    for buy in buys:
        record = records.get((buy.symbol, buy.signal_timestamp))
        if record is not None:
            without_condition += not record.entry_condition_met
            conflicts += (
                record.sell_score is not None
                and record.sell_score >= strategy.config.sell_score
            )
            forced += record.forced
        following = next(
            (
                record
                for record in strategy.records
                if record.symbol == buy.symbol
                and record.evaluation_timestamp >= buy.timestamp
            ),
            None,
        )
        if following is None:
            continue
        next_general += any(
            fill.side == "sell"
            and fill.symbol == buy.symbol
            and fill.signal_timestamp == following.evaluation_timestamp
            and not protected.intersection(fill.reasons)
            for fill in result.trades
        )
    complete = []
    for month in performance.months:
        year, number = (int(value) for value in month.month.split("-"))
        first = f"{month.month}-01"
        last = f"{month.month}-{calendar.monthrange(year, number)[1]:02d}"
        if split.start[:10] <= first and split.end[:10] >= last:
            complete.append(month)
    realized = sum(fill.pnl for fill in result.trades if fill.side == "sell")
    return EntryOutcome(
        without_condition,
        conflicts,
        forced,
        next_general,
        None,
        realized,
        result.ending_value - result.starting_cash - realized,
        len(complete),
        sum(month.usd_return_pct >= 10 for month in complete),
        "insufficient_full_months"
        if not complete
        else "observed_months_not_future_probability",
    )


def monthly_rows(
    performance: Performance, split: EvaluationSplit
) -> list[dict[str, str | int | float | bool | None]]:
    result = []
    for month in performance.months:
        year, number = (int(value) for value in month.month.split("-"))
        first, last = (
            f"{month.month}-01",
            f"{month.month}-{calendar.monthrange(year, number)[1]:02d}",
        )
        result.append(
            asdict(month)
            | {
                "complete_calendar_window": split.start[:10] <= first
                and split.end[:10] >= last
            }
        )
    return result
