from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditEvent, NullAuditLogger
from nasdaq_auto_trader.ai_quant_lab.backtest_market_data import (
    validate_backtest_market_data,
)
from nasdaq_auto_trader.ai_quant_lab.backtest_metrics import (
    MetricTiming,
    calculate_backtest_metrics,
)
from nasdaq_auto_trader.ai_quant_lab.backtest_position_state import OpenPosition
from nasdaq_auto_trader.ai_quant_lab.backtest_sizing import backtest_position_quantity
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import StrategySpec
from nasdaq_auto_trader.quant_data.feature_statistics import normalized_timestamps
from nasdaq_auto_trader.quant_data.features import PriceBar, calculate_feature_rows
from nasdaq_auto_trader.strategies.strategy_library import build_strategy


@dataclass(frozen=True, slots=True)
class TradeLog:
    symbol: str
    side: str
    timestamp: str
    price: float
    qty: int
    cost: float


@dataclass(frozen=True, slots=True)
class BacktestResult:
    experiment_id: str
    strategy_id: str
    success: bool
    metrics: Mapping[str, float]
    trades: tuple[TradeLog, ...]
    equity_curve: tuple[float, ...]
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BacktestRequest:
    """Daily-bar simulation; subdaily and sparse weekly/monthly inputs are rejected."""

    spec: StrategySpec
    bars_by_symbol: dict[str, list[PriceBar]]
    initial_cash: float = 100_000.0
    benchmark_symbol: str = "QQQ"
    trade_start_index: int = 1


class BacktestEngine:
    def __init__(
        self,
        config: AIQuantConfig | None = None,
        audit_logger: NullAuditLogger | None = None,
    ) -> None:
        self.config = config or AIQuantConfig()
        self.audit_logger = audit_logger or NullAuditLogger()

    def run(self, request: BacktestRequest) -> BacktestResult:
        experiment_id = str(uuid4())
        self.audit_logger.append(
            AuditEvent(
                "backtest_started",
                experiment_id=experiment_id,
                strategy_id=request.spec.strategy_id,
                strategy_version=request.spec.version,
            )
        )
        bars_count, market_data_reason = validate_backtest_market_data(
            request.bars_by_symbol,
            request.initial_cash,
        )
        if market_data_reason is not None:
            return self._failed(request, experiment_id, market_data_reason)
        if not 1 <= request.trade_start_index < bars_count - 1:
            return self._failed(request, experiment_id, "invalid_trade_start_index")
        strategy = build_strategy(request.spec)
        cash = request.initial_cash
        positions: dict[str, int] = {}
        open_positions: dict[str, OpenPosition] = {}
        trades: list[TradeLog] = []
        equity_curve: list[float] = [cash, cash]
        for index in range(1, bars_count - 1):
            if index < request.trade_start_index:
                equity_curve.append(cash)
                continue
            known = {
                symbol: bars[: index + 1]
                for symbol, bars in request.bars_by_symbol.items()
                if len(bars) > index + 1
            }
            features = calculate_feature_rows(known, request.benchmark_symbol)
            ranked = strategy.rank_and_select(strategy.generate_signals(features))
            targets = {
                target.symbol: target
                for target in strategy.generate_target_positions(ranked)
            }
            next_index = index + 1
            exited_symbols: set[str] = set()
            for symbol in tuple(positions):
                current_price = request.bars_by_symbol[symbol][index].close
                observed = open_positions[symbol].observe(current_price)
                open_positions[symbol] = observed
                if (
                    symbol in targets
                    and not observed.should_exit(
                        current_price,
                        index,
                        request.spec.exit_rule,
                    )
                ):
                    continue
                next_bar = request.bars_by_symbol[symbol][next_index]
                qty = positions.pop(symbol)
                fill_price = _sell_fill_price(next_bar.open, self.config)
                proceeds = fill_price * qty
                cash += proceeds
                open_positions.pop(symbol)
                exited_symbols.add(symbol)
                trades.append(
                    TradeLog(symbol, "sell", next_bar.timestamp, fill_price, qty, proceeds)
                )
            for target in targets.values():
                if target.symbol in positions or target.symbol in exited_symbols:
                    continue
                next_bar = request.bars_by_symbol[target.symbol][index + 1]
                fill_price = _buy_fill_price(next_bar.open, self.config)
                risk_distance = max(target.entry_price - target.stop_price, 0.01)
                portfolio_equity = _mark_to_market(
                    cash,
                    positions,
                    request.bars_by_symbol,
                    next_index,
                    at_open=True,
                )
                qty = backtest_position_quantity(
                    request.spec.position_sizing,
                    target.position_strength,
                    fill_price,
                    risk_distance,
                    portfolio_equity,
                    cash,
                )
                if qty < 1:
                    continue
                if cash < fill_price * qty:
                    continue
                cash -= fill_price * qty
                positions[target.symbol] = qty
                open_positions[target.symbol] = OpenPosition(
                    fill_price,
                    next_index,
                    fill_price,
                    risk_distance,
                )
                trades.append(
                    TradeLog(target.symbol, "buy", next_bar.timestamp, fill_price, qty, fill_price * qty)
                )
            equity_curve.append(
                _mark_to_market(
                    cash,
                    positions,
                    request.bars_by_symbol,
                    next_index,
                )
            )
        for symbol, qty in tuple(positions.items()):
            last_bar = request.bars_by_symbol[symbol][-1]
            fill_price = _sell_fill_price(last_bar.close, self.config)
            proceeds = fill_price * qty
            cash += proceeds
            trades.append(
                TradeLog(symbol, "sell", last_bar.timestamp, fill_price, qty, proceeds)
            )
        equity_curve[-1] = cash
        timestamps = normalized_timestamps(next(iter(request.bars_by_symbol.values())))
        timing = MetricTiming(timestamps, 252.0) if timestamps is not None else None
        metrics = calculate_backtest_metrics(equity_curve, trades, timing).to_mapping()
        result = BacktestResult(
            experiment_id=experiment_id,
            strategy_id=request.spec.strategy_id,
            success=True,
            metrics=metrics,
            trades=tuple(trades),
            equity_curve=tuple(equity_curve),
        )
        self.audit_logger.append(
            AuditEvent(
                "backtest_completed",
                experiment_id=experiment_id,
                strategy_id=request.spec.strategy_id,
                payload={"trade_count": len(trades), "total_return": metrics["total_return"]},
            )
        )
        return result

    def _failed(
        self,
        request: BacktestRequest,
        experiment_id: str,
        reason: str,
    ) -> BacktestResult:
        result = BacktestResult(
            experiment_id=experiment_id,
            strategy_id=request.spec.strategy_id,
            success=False,
            metrics={},
            trades=(),
            equity_curve=(),
            rejection_reasons=(reason,),
        )
        self.audit_logger.append(
            AuditEvent(
                "backtest_completed",
                severity="error",
                experiment_id=experiment_id,
                strategy_id=request.spec.strategy_id,
                payload={"success": False},
                error=reason,
            )
        )
        return result


def _buy_fill_price(price: float, config: AIQuantConfig) -> float:
    return price * (1 + (config.slippage_bps + config.commission_bps) / 10_000)


def _sell_fill_price(price: float, config: AIQuantConfig) -> float:
    return price * (1 - (config.slippage_bps + config.commission_bps) / 10_000)


def _mark_to_market(
    cash: float,
    positions: dict[str, int],
    bars_by_symbol: dict[str, list[PriceBar]],
    index: int,
    at_open: bool = False,
) -> float:
    value = cash
    for symbol, qty in positions.items():
        bar = bars_by_symbol[symbol][index]
        value += qty * (bar.open if at_open else bar.close)
    return value
