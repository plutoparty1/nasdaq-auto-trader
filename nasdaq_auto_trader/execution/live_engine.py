from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import StrategySpec, validate_strategy_spec
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.execution.kill_switch import KillSwitch, KillSwitchState
from nasdaq_auto_trader.execution.order_executor import BrokerOrderClient, OrderExecutor
from nasdaq_auto_trader.execution.position_sizer import PortfolioState, PositionSizer, SizingRequest
from nasdaq_auto_trader.execution.risk_guard import (
    MarketHealth,
    OrderIntent,
    RiskGuard,
    RiskGuardContext,
)
from nasdaq_auto_trader.quant_data.features import PriceBar, calculate_feature_rows
from nasdaq_auto_trader.strategies.strategy_library import build_strategy


class LiveMarketData(Protocol):
    def latest_bars(self) -> dict[str, list[PriceBar]]: ...

    def market_health(self, symbol: str) -> MarketHealth: ...

    def portfolio_state(self) -> PortfolioState: ...


class StrategySpecStore(Protocol):
    def load(self, strategy_id: str, version: str) -> StrategySpec | None: ...


@dataclass(frozen=True, slots=True)
class LiveEngineResult:
    status: str
    submitted_orders: int
    blocked_reasons: tuple[str, ...]


class LiveEngine:
    def __init__(
        self,
        registry: StrategyRegistry,
        spec_store: StrategySpecStore,
        market_data: LiveMarketData,
        broker: BrokerOrderClient,
        risk_guard: RiskGuard | None = None,
        position_sizer: PositionSizer | None = None,
        order_executor: OrderExecutor | None = None,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        self.registry = registry
        self.spec_store = spec_store
        self.market_data = market_data
        self.broker = broker
        self.risk_guard = risk_guard or RiskGuard()
        self.position_sizer = position_sizer or PositionSizer(registry.config)
        self.order_executor = order_executor or OrderExecutor()
        self.kill_switch = kill_switch or KillSwitch()

    def run_cycle(self, kill_switch_state: KillSwitchState | None = None) -> LiveEngineResult:
        promoted = self.registry.load_promoted_strategy()
        if promoted is None:
            return LiveEngineResult("blocked", 0, ("promoted_strategy_missing",))
        strategy_id = _string(promoted.get("active_strategy_id"))
        version = _string(promoted.get("strategy_version"))
        spec = self.spec_store.load(strategy_id, version)
        if spec is None:
            return LiveEngineResult("blocked", 0, ("strategy_spec_missing",))
        validation = validate_strategy_spec(spec.raw)
        if not validation.valid:
            return LiveEngineResult("blocked", 0, ("strategy_spec_invalid",))
        bars = self.market_data.latest_bars()
        features = calculate_feature_rows(bars)
        strategy = build_strategy(spec)
        ranked = strategy.rank_and_select(strategy.generate_signals(features))
        targets = strategy.generate_target_positions(ranked)
        portfolio = self.market_data.portfolio_state()
        kill_result = self.kill_switch.evaluate(kill_switch_state or KillSwitchState())
        submitted = 0
        blocked: list[str] = []
        reserved_cash = 0.0
        reserved_exposure = 0.0
        reserved_positions: dict[str, int] = {}
        for target in targets:
            adjusted_positions = {
                symbol: qty + reserved_positions.get(symbol, 0)
                for symbol, qty in portfolio.current_positions.items()
            }
            for symbol, qty in reserved_positions.items():
                if symbol not in adjusted_positions:
                    adjusted_positions[symbol] = qty
            adjusted_portfolio = PortfolioState(
                portfolio.account_equity,
                max(portfolio.available_cash - reserved_cash, 0.0),
                adjusted_positions,
                portfolio.current_exposure + reserved_exposure,
                portfolio.daily_loss_limit_reached,
            )
            sizing = self.position_sizer.calculate(
                SizingRequest(target, adjusted_portfolio, target.entry_price)
            )
            symbol_position_value = adjusted_positions.get(target.symbol, 0) * target.entry_price
            intent = OrderIntent(
                strategy_id=target.strategy_id,
                symbol=target.symbol,
                side=target.side,
                order_qty=sizing.order_qty,
                current_price=target.entry_price,
                notional=sizing.notional,
            )
            guard = self.risk_guard.check(
                RiskGuardContext(
                    config=self.registry.config,
                    intent=intent,
                    promoted_strategy=promoted,
                    market=self.market_data.market_health(target.symbol),
                    current_positions=adjusted_positions,
                    available_cash=adjusted_portfolio.available_cash,
                    total_exposure=adjusted_portfolio.current_exposure,
                    account_equity=adjusted_portfolio.account_equity,
                    symbol_position_value=symbol_position_value,
                    single_position_exposure=symbol_position_value / adjusted_portfolio.account_equity
                    if adjusted_portfolio.account_equity > 0
                    else 0.0,
                    kill_switch=kill_result,
                )
            )
            response = self.order_executor.submit_after_risk_guard(self.broker, intent, guard)
            status = _string(response.get("status"))
            if status == "blocked":
                blocked.append(_string(response.get("reason")) or "order_blocked")
            elif status in ("submitted", "accepted", "filled", "fake_submitted"):
                submitted += 1
                if intent.side == "buy":
                    reserved_cash += intent.notional
                    reserved_exposure += intent.notional
                    reserved_positions[intent.symbol] = (
                        reserved_positions.get(intent.symbol, 0) + intent.order_qty
                    )
            else:
                blocked.append(_string(response.get("reason")) or "order_response_not_submitted")
        return LiveEngineResult(
            status="completed" if submitted else "blocked",
            submitted_orders=submitted,
            blocked_reasons=tuple(blocked),
        )


def _string(value: JsonObject | str | int | float | bool | None) -> str:
    return value.strip() if isinstance(value, str) else ""
