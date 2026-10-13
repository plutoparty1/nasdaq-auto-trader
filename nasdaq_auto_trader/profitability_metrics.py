from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median

from .backtest_types import BacktestResult
from .entry_comparison_metrics import monthly_rows
from .exit_experiment import EvaluationSplit
from .exit_experiment_metrics import Performance


@dataclass(frozen=True, slots=True)
class AdditionalSummary:
    evaluation_start: str
    evaluation_end: str
    first_equity_timestamp: str | None
    last_equity_timestamp: str | None
    equity_observations: int
    evaluation_days_observed: int
    completed_roundtrips: int
    buy_fills: int
    sell_fills: int
    net_pnl_usd: float
    gross_pnl_before_model_costs_usd: float
    gross_pnl_definition: str
    realized_pnl_usd: float
    unrealized_pnl_after_entry_cost_usd: float
    average_net_completed_trade_usd: float | None
    average_invested_pct: float
    maximum_invested_pct: float
    average_cash_pct: float
    minimum_cash_pct: float
    maximum_cash_pct: float
    exposure_sampling: str
    commissions_usd: float
    execution_cost_usd: float
    total_trading_cost_usd: float
    complete_calendar_months: int
    target_complete_calendar_months: int
    complete_month_median_return_pct: float | None
    complete_month_worst_return_pct: float | None
    observed_months: int
    observed_month_median_return_pct: float | None
    observed_month_worst_return_pct: float | None
    monthly_evidence_status: str


def additional_summary(
    result: BacktestResult, performance: Performance, split: EvaluationSplit
) -> AdditionalSummary:
    """Add snapshot exposure and full-calendar statistics without annualization."""
    complete = [
        month.usd_return_pct
        for month, row in zip(performance.months, monthly_rows(performance, split), strict=True)
        if row["complete_calendar_window"]
    ]
    observed = [month.usd_return_pct for month in performance.months]
    invested = [100 * point.positions_value / point.equity for point in result.equity_curve
                if point.equity > 0]
    cash = [100 * point.cash / point.equity for point in result.equity_curve
            if point.equity > 0]
    quantities: dict[str, float] = {}
    profits: dict[str, float] = {}
    closed: list[float] = []
    for trade in result.trades:
        if trade.side == "buy":
            if quantities.get(trade.symbol, 0) <= 1e-10:
                profits[trade.symbol] = 0.0
            quantities[trade.symbol] = quantities.get(trade.symbol, 0) + trade.qty
        else:
            quantities[trade.symbol] -= trade.qty
            profits[trade.symbol] += trade.pnl
            if quantities[trade.symbol] <= 1e-10:
                closed.append(profits[trade.symbol])
    net = result.ending_value - result.starting_cash
    realized = sum(trade.pnl for trade in result.trades if trade.side == "sell")
    costs = performance.summary
    return AdditionalSummary(
        evaluation_start=split.start,
        evaluation_end=split.end,
        first_equity_timestamp=result.equity_curve[0].timestamp if result.equity_curve else None,
        last_equity_timestamp=result.equity_curve[-1].timestamp if result.equity_curve else None,
        equity_observations=len(result.equity_curve),
        evaluation_days_observed=len({point.timestamp[:10] for point in result.equity_curve}),
        completed_roundtrips=len(closed),
        buy_fills=sum(trade.side == "buy" for trade in result.trades),
        sell_fills=sum(trade.side == "sell" for trade in result.trades),
        net_pnl_usd=net,
        gross_pnl_before_model_costs_usd=net + costs.trading_cost_usd,
        gross_pnl_definition="observed_path_net_plus_commissions_and_execution_impact_not_counterfactual",
        realized_pnl_usd=realized,
        unrealized_pnl_after_entry_cost_usd=net - realized,
        average_net_completed_trade_usd=mean(closed) if closed else None,
        average_invested_pct=mean(invested) if invested else 0.0,
        maximum_invested_pct=max(invested, default=0.0),
        average_cash_pct=mean(cash) if cash else 100.0,
        minimum_cash_pct=min(cash, default=100.0),
        maximum_cash_pct=max(cash, default=100.0),
        exposure_sampling="equal_weight_per_equity_observation_not_elapsed_time_weighted",
        commissions_usd=costs.commissions_usd,
        execution_cost_usd=costs.execution_cost_usd,
        total_trading_cost_usd=costs.trading_cost_usd,
        complete_calendar_months=len(complete),
        target_complete_calendar_months=sum(value >= 10 - 1e-9 for value in complete),
        complete_month_median_return_pct=median(complete) if complete else None,
        complete_month_worst_return_pct=min(complete) if complete else None,
        observed_months=len(observed),
        observed_month_median_return_pct=median(observed) if observed else None,
        observed_month_worst_return_pct=min(observed) if observed else None,
        monthly_evidence_status="observed_months_not_future_probability" if complete else "insufficient_full_months",
    )
