from dataclasses import dataclass, field

import pytest

from nasdaq_auto_trader.backtest import BacktestCosts, Backtester
from nasdaq_auto_trader.models import (
    AccountSnapshot,
    Bar,
    OrderRequest,
    Position,
    TradeDecision,
)
from nasdaq_auto_trader.risk import RiskManager
from tests import test_early_exit_backtest as offline_fixtures
from tests.test_early_exit_backtest import (
    ScriptedStrategy,
    bars,
    risk_manager,
)

deny_network = offline_fixtures.deny_network

pytestmark = pytest.mark.usefixtures("deny_network")


class MarketOrders(RiskManager):
    def __init__(self, qty: float = 1) -> None:
        super().__init__()
        self.qty = qty

    def build_order(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        position: Position | None,
        latest_price: float,
    ) -> OrderRequest | None:
        match decision.action:
            case "hold":
                return None
            case "buy" | "sell":
                return OrderRequest(decision.symbol, decision.action, qty=self.qty)


@pytest.mark.parametrize(("step", "count"), [(1, 0), (0.1, 1)])
def test_quantity_step_matches_explicit_fractional_support(
    step: float, count: int
) -> None:
    # Given a half-share request under an explicit broker quantity step.
    engine = Backtester(
        ScriptedStrategy({0: "buy"}),
        MarketOrders(0.5),
        costs=BacktestCosts(quantity_step=step),
    )
    # When a future bar is available.
    result = engine.run({"TEST": bars([10, 10])}, 100)
    # Then integer-only rejects while one-tenth precision fills exactly half a share.
    assert len(result.trades) == count
    if count:
        assert result.trades[0].qty == 0.5
    else:
        assert result.rejections[0].reason == "invalid_quantity_or_step"


def test_minimum_fees_are_allocated_proportionally_on_partial_sale() -> None:
    # Given two entries (10 and 20), then one partial sale at 30 with $1 each fill.
    strategy = ScriptedStrategy({0: "buy", 1: "buy", 2: "sell"})
    engine = Backtester(
        strategy,
        MarketOrders(),
        costs=BacktestCosts(minimum_commission=1, quantity_step=1),
    )
    # When the position is marked after the partial sale.
    result = engine.run({"TEST": bars([10, 10, 20, 30])}, 100)
    # Then only half the total entry fees attach to that sale; residual remains marked.
    sale = result.trades[-1]
    assert (sale.gross_pnl, sale.allocated_entry_fee, sale.fee, sale.pnl) == (
        15,
        1,
        1,
        13,
    )
    assert result.ending_positions[0].qty == 1
    assert result.ending_positions[0].avg_entry_price == 15
    assert result.ending_value == 127


def test_notional_order_floors_after_reserving_fee() -> None:
    # Given $25 cash with a $1 commission and integer-only market orders.
    engine = Backtester(
        ScriptedStrategy({0: "buy"}),
        risk_manager(None),
        costs=BacktestCosts(minimum_commission=1, quantity_step=1),
    )
    # When one share costs $10.
    result = engine.run({"TEST": bars([10, 10])}, 25)
    # Then two shares plus the fee leave four dollars, never a fractional remainder.
    assert result.trades[0].qty == 2
    assert result.equity_curve[-1].cash == 4
    assert result.ending_value == 24


def test_gtc_limit_survives_without_duplicate_replacement_until_touched() -> None:
    # Given a resting limit buy at 10 while another signal would also buy.
    class GtcOrders(MarketOrders):
        def build_order(
            self,
            decision: TradeDecision,
            account: AccountSnapshot,
            position: Position | None,
            latest_price: float,
        ) -> OrderRequest | None:
            return OrderRequest(
                decision.symbol,
                "buy",
                type="limit",
                time_in_force="gtc",
                qty=1,
                limit_price=10,
            )

    engine = Backtester(ScriptedStrategy({0: "buy", 1: "buy"}), GtcOrders())
    # When only the second following bar touches and opens below the limit.
    result = engine.run({"TEST": bars([10, 12, 9])}, 100)
    # Then the original signal owns the single fill at the better opening price.
    assert len(result.trades) == 1
    assert (
        result.trades[0].signal_timestamp,
        result.trades[0].timestamp,
        result.trades[0].price,
    ) == ("T000", "T002", 9)


def test_limit_touch_fills_at_limit_and_never_worse_after_costs() -> None:
    # Given a 10 limit, opening 12 and intrabar low 9.
    path = [bars([10])[0], Bar("TEST", "T001", 12, 12, 9, 11, 1000)]
    # When a nonzero impact assumption is applied.
    result = Backtester(
        ScriptedStrategy({0: "buy"}),
        risk_manager(),
        costs=BacktestCosts(spread_bps=20, slippage_bps=10),
    ).run({"TEST": path}, 100)
    # Then the limit remains an upper bound; the unknown touch time is not fabricated.
    assert result.trades[0].price == 10
    assert result.ending_positions[0].high_water_price == 11


def test_adverse_gap_cannot_violate_actual_fill_risk_budget() -> None:
    # Given a one-dollar risk estimate using the full 1% budget of a $100 account.
    engine = Backtester(
        ScriptedStrategy({0: "buy"}, risk=1), MarketOrders(), max_trade_risk_pct=0.01
    )
    # When the next open gaps two dollars higher.
    result = engine.run({"TEST": bars([10, 12])}, 100)
    # Then the cap is checked again at fill and the order is skipped.
    assert not result.trades
    assert result.rejections[0].reason == "portfolio_risk_limit_at_fill"


@dataclass
class FillObserver:
    stop: float | None = 8
    entries: list[tuple[str, float, float, str]] = field(default_factory=list)
    exits: list[tuple[str, float]] = field(default_factory=list)

    def initial_stop_for(self, symbol: str, fill_price: float) -> float | None:
        return self.stop

    def register_entry_fill(
        self, symbol: str, price: float, qty: float, timestamp: str
    ) -> None:
        self.entries.append((symbol, price, qty, timestamp))

    def register_exit_fill(self, symbol: str, remaining_qty: float) -> None:
        self.exits.append((symbol, remaining_qty))


def test_fill_observer_sees_actual_average_total_quantity_and_residual() -> None:
    # Given entry, additional buy and partial sale signals.
    observer = FillObserver()
    engine = Backtester(
        ScriptedStrategy({0: "buy", 1: "buy", 2: "sell"}),
        MarketOrders(),
        fill_observer=observer,
    )
    # When fills happen at 10, 20 and 30.
    engine.run({"TEST": bars([10, 10, 20, 30])}, 100)
    # Then callbacks identify filled state rather than submitted orders.
    assert observer.entries == [("TEST", 10, 1, "T001"), ("TEST", 15, 2, "T002")]
    assert observer.exits == [("TEST", 1)]


def test_unusable_entry_stop_refuses_fill_without_callback() -> None:
    # Given unavailable entry ATR represented by no valid stop.
    observer = FillObserver(stop=None)
    engine = Backtester(
        ScriptedStrategy({0: "buy"}), MarketOrders(), fill_observer=observer
    )
    # When the next bar otherwise permits a fill.
    result = engine.run({"TEST": bars([10, 10])}, 100)
    # Then no position state or cash moves.
    assert not result.trades
    assert not observer.entries
    assert result.rejections[0].reason == "invalid_initial_stop_at_fill"


def test_last_bar_signal_is_unfilled() -> None:
    # Given no subsequent execution timestamp.
    engine = Backtester(ScriptedStrategy({0: "buy"}), MarketOrders())
    # When the sole bar generates a buy.
    result = engine.run({"TEST": bars([10])}, 100)
    # Then the result records the unfinished signal instead of fabricating a fill.
    assert not result.trades
    assert result.rejections[0].reason == "end_of_data_unfilled"


def test_cost_free_risk_distance_still_reserves_round_trip_commissions() -> None:
    # Given a $1 price risk and $1 minimum commissions, the $2 budget is too small.
    engine = Backtester(
        ScriptedStrategy({0: "buy"}, risk=1),
        MarketOrders(),
        costs=BacktestCosts(minimum_commission=1),
        max_trade_risk_pct=0.02,
    )
    # When the risk distance excludes costs as ordinary RiskManager decisions do.
    result = engine.run({"TEST": bars([10, 10])}, 100)
    # Then planned $3 net loss cannot pass as $1 risk.
    assert not result.trades


def test_preincluded_cost_risk_is_not_charged_twice() -> None:
    # Given an explicit $3 risk already including both $1 fees and $1 stop distance.
    engine = Backtester(
        ScriptedStrategy({0: "buy"}, risk=3),
        MarketOrders(),
        costs=BacktestCosts(minimum_commission=1),
        max_trade_risk_pct=0.04,
        risk_includes_costs=True,
    )
    # When the $4 budget can fund the total risk.
    result = engine.run({"TEST": bars([10, 10])}, 100)
    # Then the trade fills without double-counting the commission budget.
    assert len(result.trades) == 1
