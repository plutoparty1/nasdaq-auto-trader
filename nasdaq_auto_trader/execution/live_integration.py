from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditLogger
from nasdaq_auto_trader.ai_quant_lab.artifact_paths import default_strategy_artifact_paths
from nasdaq_auto_trader.ai_quant_lab.config import (
    AIQuantConfig,
    live_order_block_reason,
    load_ai_quant_config,
    validate_ai_quant_config,
)
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.storage import safe_artifact_path
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import (
    StrategySpec,
    parse_strategy_spec_json,
)
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject, JsonValue
from nasdaq_auto_trader.broker_response import broker_response_status
from nasdaq_auto_trader.config import AppConfig, validate_trading_mode
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.execution.live_engine import LiveEngine, LiveEngineResult
from nasdaq_auto_trader.execution.position_sizer import PortfolioState
from nasdaq_auto_trader.execution.risk_guard import MarketHealth, OrderIntent, RiskGuard
from nasdaq_auto_trader.models import AccountSnapshot, Bar, OrderRequest, Position
from nasdaq_auto_trader.quant_data.features import PriceBar

MAX_LIVE_SPREAD_BPS: Final = 100.0


class LegacyBroker(Protocol):
    def submit_order(self, order: OrderRequest) -> JsonObject: ...


class LegacyMarketData(Protocol):
    def get_stock_bars(
        self,
        symbols: list[str],
        timeframe: str,
        start: str,
        end: str | None = None,
        limit: int = 1000,
    ) -> dict[str, list[Bar]]: ...

    def get_account(self) -> AccountSnapshot: ...

    def list_positions(self) -> dict[str, Position]: ...


@runtime_checkable
class QuoteMarketData(Protocol):
    def get_best_quote(self, symbol: str) -> JsonObject: ...


class LegacyTradingEngine(Protocol):
    broker: LegacyBroker
    market_data: LegacyMarketData


class LegacyEngineFactory(Protocol):
    def __call__(self, config: AppConfig) -> LegacyTradingEngine: ...


@dataclass(frozen=True, slots=True)
class AIQuantRuntimePaths:
    ai_config_path: Path | None = field(
        default_factory=lambda: default_strategy_artifact_paths().ai_config_path
    )
    registry_path: Path = field(
        default_factory=lambda: default_strategy_artifact_paths().registry_path
    )
    promoted_path: Path = field(
        default_factory=lambda: default_strategy_artifact_paths().promoted_path
    )
    spec_dir: Path = field(
        default_factory=lambda: default_strategy_artifact_paths().spec_dir
    )
    audit_log_path: Path = field(
        default_factory=lambda: default_strategy_artifact_paths().audit_log_path
    )


@dataclass(frozen=True, slots=True)
class AIQuantLiveEngineContext:
    app_config: AppConfig
    ai_config: AIQuantConfig
    paths: AIQuantRuntimePaths
    existing_engine: LegacyTradingEngine


class FileStrategySpecStore:
    def __init__(self, spec_dir: str | Path) -> None:
        self.spec_dir = Path(spec_dir)

    def load(self, strategy_id: str, version: str) -> StrategySpec | None:
        try:
            path = safe_artifact_path(self.spec_dir, f"{strategy_id}-{version}", ".json")
            validation = parse_strategy_spec_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return validation.spec


@dataclass(frozen=True, slots=True)
class ExistingBrokerOrderAdapter:
    broker: LegacyBroker

    def submit_order(self, intent: OrderIntent) -> JsonObject:
        order = OrderRequest(
            symbol=intent.symbol,
            side="sell" if intent.side == "sell" else "buy",
            type="limit",
            qty=float(intent.order_qty),
            limit_price=float(intent.current_price),
        )
        broker_response = self.broker.submit_order(order)
        return {
            "status": broker_response_status(broker_response),
            "broker_status": _string(broker_response.get("status")),
            "order": order.to_alpaca_payload(),
            "broker_response": broker_response,
        }


@dataclass(frozen=True, slots=True)
class ExistingEngineMarketDataAdapter:
    app_config: AppConfig
    market_data: LegacyMarketData
    ai_config: AIQuantConfig

    def latest_bars(self) -> dict[str, list[PriceBar]]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.app_config.lookback_days)
        legacy_bars = self.market_data.get_stock_bars(
            self.app_config.symbols,
            self.app_config.timeframe,
            start.date().isoformat(),
            end.date().isoformat(),
            self.app_config.bar_limit,
        )
        return {
            symbol: [_price_bar(bar) for bar in rows]
            for symbol, rows in legacy_bars.items()
        }

    def market_health(self, symbol: str) -> MarketHealth:
        if not self.ai_config.spread_filter_enabled:
            return MarketHealth()
        if not isinstance(self.market_data, QuoteMarketData):
            return MarketHealth(price_available=False, spread_abnormal=True)
        try:
            quote = self.market_data.get_best_quote(symbol)
        except (RuntimeError, OSError, ValueError):
            return MarketHealth(
                price_available=False,
                spread_abnormal=True,
                api_error_limit_reached=True,
            )
        bid = _first_float(quote, "pbid1", "bid")
        ask = _first_float(quote, "pask1", "ask")
        if bid <= 0 or ask <= 0 or ask < bid:
            return MarketHealth(price_available=False, spread_abnormal=True)
        return MarketHealth(spread_abnormal=_spread_bps(bid, ask) > MAX_LIVE_SPREAD_BPS)

    def portfolio_state(self) -> PortfolioState:
        account = self.market_data.get_account()
        positions = self.market_data.list_positions()
        current_positions = {
            symbol: max(int(position.qty), 0)
            for symbol, position in positions.items()
        }
        current_exposure = sum(max(position.market_value, 0.0) for position in positions.values())
        return PortfolioState(
            account_equity=account.equity,
            available_cash=max(min(account.cash, account.buying_power), 0.0),
            current_positions=current_positions,
            current_exposure=current_exposure,
        )


def run_ai_quant_live_cycle(
    app_config: AppConfig,
    paths: AIQuantRuntimePaths | None = None,
    engine_factory: LegacyEngineFactory = TradingEngine,
) -> LiveEngineResult:
    runtime_paths = paths or AIQuantRuntimePaths()
    ai_config = load_ai_quant_config(runtime_paths.ai_config_path)
    validation = validate_ai_quant_config(ai_config)
    if not validation.valid:
        return LiveEngineResult("blocked", 0, validation.reasons)
    reason = live_order_block_reason(ai_config)
    if reason is not None:
        return LiveEngineResult("blocked", 0, (reason,))
    app_reason = _app_live_block_reason(app_config)
    if app_reason is not None:
        return LiveEngineResult("blocked", 0, (app_reason,))
    return LiveEngineResult("blocked", 0, ("shared_order_gateway_required",))


def build_ai_quant_live_engine(context: AIQuantLiveEngineContext) -> LiveEngine:
    audit_logger = AuditLogger(context.paths.audit_log_path)
    registry = StrategyRegistry(
        context.paths.registry_path,
        context.paths.promoted_path,
        config=context.ai_config,
        audit_logger=audit_logger,
    )
    return LiveEngine(
        registry,
        FileStrategySpecStore(context.paths.spec_dir),
        ExistingEngineMarketDataAdapter(
            context.app_config,
            context.existing_engine.market_data,
            context.ai_config,
        ),
        ExistingBrokerOrderAdapter(context.existing_engine.broker),
        risk_guard=RiskGuard(audit_logger),
    )


def _app_live_block_reason(config: AppConfig) -> str | None:
    if config.mode != "live":
        return "app_mode_not_live"
    try:
        validate_trading_mode(config)
    except ValueError:
        return "app_config_invalid"
    return None


def _price_bar(bar: Bar) -> PriceBar:
    return PriceBar(
        symbol=bar.symbol,
        timestamp=bar.timestamp,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
    )


def _string(value: JsonValue) -> str:
    return value.strip() if isinstance(value, str) else ""


def _first_float(payload: JsonObject, *keys: str) -> float:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            continue
    return 0.0


def _spread_bps(bid: float, ask: float) -> float:
    midpoint = (bid + ask) / 2
    return (ask - bid) / midpoint * 10_000 if midpoint > 0 else MAX_LIVE_SPREAD_BPS + 1
