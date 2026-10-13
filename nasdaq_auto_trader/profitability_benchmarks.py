from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final, TypedDict

from .backtest_costs import BacktestCosts
from .backtest_types import BacktestResult, BacktestTrade, EquityPoint
from .exit_experiment import EvaluationSplit
from .exit_experiment_config import ExperimentInputError
from .models import Bar, OrderRequest, Position

POSITION_LIMIT: Final = 0.5
CASH_BUFFER: Final = 0.05
MAX_ORDER_USD: Final = 35.0


@dataclass(frozen=True, slots=True)
class SymbolFeasibility:
    symbol: str
    signal_timestamp: str
    entry_timestamp: str | None
    reference_open_usd: float | None
    entry_price_usd: float | None
    one_share_commission_usd: float | None
    allocated_cash_usd: float
    one_share_cash_required_usd: float | None
    acquired_qty: int
    blocking_reasons: tuple[str, ...]
    required_initial_cash_usd: float | None
    required_max_order_notional_usd: float | None


@dataclass(frozen=True, slots=True)
class BasketFeasibility:
    symbols: tuple[SymbolFeasibility, ...]
    full_basket_one_share_outlay_usd: float | None
    full_basket_required_initial_cash_usd: float | None
    full_basket_required_max_order_notional_usd: float | None
    full_basket_available: bool
    planned_stop_risk: str = "not_defined_for_passive_hold_no_stop_protection"


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    result: BacktestResult
    status: str
    included_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...]
    feasibility: BasketFeasibility
    notes: tuple[str, ...]
    estimated_liquidation_value_usd: float


class BenchmarkSet(TypedDict):
    usd_cash: BenchmarkCase
    integer_buy_hold: BenchmarkCase
    fractional_reference: BenchmarkCase


def build_benchmarks(
    bars: Mapping[str, Sequence[Bar]], split: EvaluationSplit,
    costs: BacktestCosts, starting_cash: float,
) -> BenchmarkSet:
    """Order at first evaluation close, fill next open; fractional returns are references."""
    selected = {symbol: sorted((bar for bar in history if split.start <= bar.timestamp <= split.end),
                               key=lambda bar: bar.timestamp) for symbol, history in bars.items()}
    if not selected or any(not history for history in selected.values()):
        raise ExperimentInputError("benchmark needs an evaluation bar for every frozen symbol")
    if costs.quantity_step != 1:
        raise ExperimentInputError("benchmark requires the verified whole-share quantity step")
    events: dict[str, list[Bar]] = defaultdict(list)
    for history in selected.values():
        for bar in history:
            events[bar.timestamp].append(bar)
    allocation = starting_cash / len(selected)
    cash, reference_cash = starting_cash, starting_cash
    trades: list[BacktestTrade] = []
    positions: dict[str, Position] = {}
    reference_positions: dict[str, float] = {}
    last_prices: dict[str, float] = {}
    curve: list[EquityPoint] = []
    reference_curve: list[EquityPoint] = []
    feasibility: list[SymbolFeasibility] = []
    for timestamp, current in sorted(events.items()):
        for bar in current:
            last_prices[bar.symbol] = bar.open
            if bar.symbol in positions:
                positions[bar.symbol] = replace(positions[bar.symbol], market_value=bar.open)
        for bar in sorted(current, key=lambda item: item.symbol):
            history = selected[bar.symbol]
            if len(history) < 2:
                feasibility.append(SymbolFeasibility(
                    bar.symbol, history[0].timestamp, None, None, None, None,
                    allocation, None, 0, ("no_next_bar_after_signal",), None, None,
                ))
                continue
            if timestamp != history[1].timestamp:
                continue
            fill = costs.fill_price(OrderRequest(bar.symbol, "buy", qty=1), bar)
            if fill is None:
                raise ExperimentInputError("market benchmark fill could not be priced")
            price, impact = fill
            fee, outlay = costs.fee(price), price + costs.fee(price)
            holdings = sum(position.market_value for position in positions.values())
            equity = cash + holdings
            checks = (
                (outlay > allocation + 1e-10, "equal_allocation_cannot_buy_one_share"),
                (price > (equity - fee) * POSITION_LIMIT + 1e-10, "per_symbol_limit_50pct"),
                (holdings + price > (equity - fee) * POSITION_LIMIT + 1e-10, "total_exposure_limit_50pct"),
                (price > MAX_ORDER_USD + 1e-10, "max_order_notional_35usd"),
                (outlay > cash - equity * CASH_BUFFER + 1e-10, "cash_buffer_and_commission"),
            )
            blockers = tuple(reason for blocked, reason in checks if blocked)
            qty = int(not blockers)
            feasibility.append(SymbolFeasibility(
                bar.symbol, history[0].timestamp, timestamp, bar.open, price, fee, allocation, outlay, qty, blockers,
                max(len(selected) * outlay, price / POSITION_LIMIT + fee, outlay / (1 - CASH_BUFFER)),
                price,
            ))
            if qty:
                cash -= outlay
                positions[bar.symbol] = Position(bar.symbol, 1, price, price)
                trades.append(BacktestTrade(
                    history[0].timestamp, timestamp, bar.symbol, "buy", price, 1, price,
                    ("predetermined_next_open_buy_hold",), fee=fee, execution_cost=impact,
                ))
            reference_positions[bar.symbol] = allocation / bar.open
            reference_cash -= allocation
        for bar in current:
            last_prices[bar.symbol] = bar.close
            if bar.symbol in positions:
                positions[bar.symbol] = replace(positions[bar.symbol], market_value=bar.close)
        value = sum(position.market_value for position in positions.values())
        curve.append(EquityPoint(timestamp, cash + value, cash, value))
        reference_value = sum(qty * last_prices[symbol] for symbol, qty in reference_positions.items())
        reference_curve.append(EquityPoint(timestamp, reference_cash + reference_value, reference_cash, reference_value))
    records = tuple(sorted(feasibility, key=lambda item: item.symbol))
    prices = [record.entry_price_usd for record in records if record.entry_price_usd is not None]
    full_outlay = sum(record.one_share_cash_required_usd for record in records if record.one_share_cash_required_usd is not None)
    full_notional = sum(prices)
    full_priced = len(prices) == len(selected)
    required_cash = max(
        full_outlay / (1 - CASH_BUFFER), full_notional / POSITION_LIMIT + full_outlay - full_notional,
        max((record.required_initial_cash_usd for record in records if record.required_initial_cash_usd is not None), default=0.0),
    )
    basket = BasketFeasibility(
        records, full_outlay if full_priced else None, required_cash if full_priced else None,
        max(prices) if full_priced else None, len(positions) == len(selected),
    )
    included = tuple(sorted(positions))
    missing = tuple(sorted(set(selected) - set(included)))
    result = BacktestResult(starting_cash, curve[-1].equity, tuple(trades), tuple(curve),
                            ending_positions=tuple(positions[symbol] for symbol in included))
    liquidation = cash + sum(
        position.market_value * (1 - costs.adverse_fraction)
        - costs.fee(position.market_value * (1 - costs.adverse_fraction))
        for position in positions.values()
    )
    common_notes = (
        "USD_interest_0_FX_translation_only_by_external_summarize",
        "price_only_dividends_omitted_not_total_return_comparable",
        "first_evaluation_close_order_next_observed_open_fill_daily_timestamps_label_session_close",
        "market_order_with_modelled_adverse_costs_no_limit_touch_assumption",
        "end_value_marks_open_holdings_no_forced_sale_liquidation_estimate_is_separate",
        "passive_hold_has_no_stop_or_planned_loss_budget_and_is_not_a_candidate_strategy",
    )
    return {
        "usd_cash": BenchmarkCase(
            BacktestResult(starting_cash, starting_cash, equity_curve=tuple(
                EquityPoint(timestamp, starting_cash, starting_cash, 0) for timestamp in sorted(events))),
            "USD_CASH_INTEREST_ZERO", (), tuple(sorted(selected)), basket, common_notes, starting_cash,
        ),
        "integer_buy_hold": BenchmarkCase(
            result, "integer_rounded_basket" if included else ("no_trade" if prices else "no_trade_end_of_data"), included, missing, basket,
            common_notes + ("equal_initial_cash_allocations_floor_to_one_share_cap_alphabetical_no_reallocation_no_rebalance",),
            liquidation,
        ),
        "fractional_reference": BenchmarkCase(
            BacktestResult(starting_cash, reference_curve[-1].equity, equity_curve=tuple(reference_curve)),
            "NONEXECUTABLE_REFERENCE", tuple(sorted(selected)), (), basket,
            ("fractional_frictionless_equal_weight_price_only_full_investment_reference",
             "violates_integer_size_and_50pct_total_exposure_not_an_executable_account_comparator"),
            reference_curve[-1].equity,
        ),
    }
