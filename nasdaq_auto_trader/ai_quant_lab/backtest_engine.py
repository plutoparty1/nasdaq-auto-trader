from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditEvent, NullAuditLogger
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import StrategySpec
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
    metrics: dict[str, float]
    trades: tuple[TradeLog, ...]
    equity_curve: tuple[float, ...]
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BacktestRequest:
    spec: StrategySpec
    bars_by_symbol: dict[str, list[PriceBar]]
    initial_cash: float = 100_000.0
    benchmark_symbol: str = "QQQ"


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
        if not request.bars_by_symbol:
            return self._failed(request, experiment_id, "market_data_missing")
        strategy = build_strategy(request.spec)
        cash = request.initial_cash
        positions: dict[str, int] = {}
        trades: list[TradeLog] = []
        equity_curve: list[float] = [cash]
        bars_count = min(len(bars) for bars in request.bars_by_symbol.values())
        if bars_count < 3:
            return self._failed(request, experiment_id, "not_enough_bars")
        for index in range(1, bars_count - 1):
            known = {
                symbol: bars[: index + 1]
                for symbol, bars in request.bars_by_symbol.items()
                if len(bars) > index + 1
            }
            features = calculate_feature_rows(known, request.benchmark_symbol)
            ranked = strategy.rank_and_select(strategy.generate_signals(features))
            for target in strategy.generate_target_positions(ranked):
                next_bar = request.bars_by_symbol[target.symbol][index + 1]
                qty = 1
                fill_price = _cost_adjusted_price(
                    next_bar.open,
                    self.config.slippage_bps,
                    self.config.commission_bps,
                )
                if cash < fill_price * qty:
                    continue
                cash -= fill_price * qty
                positions[target.symbol] = positions.get(target.symbol, 0) + qty
                trades.append(
                    TradeLog(target.symbol, "buy", next_bar.timestamp, fill_price, qty, fill_price * qty)
                )
            equity_curve.append(_mark_to_market(cash, positions, request.bars_by_symbol, index))
        metrics = _metrics(equity_curve, trades)
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


def _cost_adjusted_price(price: float, slippage_bps: float, commission_bps: float) -> float:
    return price * (1 + (slippage_bps + commission_bps) / 10_000)


def _mark_to_market(
    cash: float,
    positions: dict[str, int],
    bars_by_symbol: dict[str, list[PriceBar]],
    index: int,
) -> float:
    value = cash
    for symbol, qty in positions.items():
        value += qty * bars_by_symbol[symbol][index].close
    return value


def _metrics(equity_curve: list[float], trades: list[TradeLog]) -> dict[str, float]:
    total_return = (equity_curve[-1] / equity_curve[0]) - 1 if len(equity_curve) > 1 else 0.0
    drawdown = _max_drawdown(equity_curve)
    returns = [
        (equity_curve[index] / equity_curve[index - 1]) - 1
        for index in range(1, len(equity_curve))
        if equity_curve[index - 1] > 0
    ]
    avg = sum(returns) / len(returns) if returns else 0.0
    variance = sum((value - avg) ** 2 for value in returns) / len(returns) if returns else 0.0
    sharpe = avg / (variance**0.5) if variance > 0 else 0.0
    return {
        "total_return": total_return,
        "cagr": total_return,
        "sharpe": sharpe,
        "sortino": sharpe,
        "max_drawdown": drawdown,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "expectancy": 0.0,
        "turnover": len(trades) / max(len(equity_curve), 1),
        "trade_count": float(len(trades)),
    }


def _max_drawdown(equity_curve: list[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, (value / peak) - 1)
    return abs(max_drawdown)
