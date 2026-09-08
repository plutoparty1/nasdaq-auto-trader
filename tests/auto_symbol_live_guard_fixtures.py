import json
from datetime import datetime, timezone

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.broker import AlpacaCredentials, KISCredentials
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.engine import TradingEngine
from nasdaq_auto_trader.live_authorization import (
    LiveAuthorizationBlock,
    LiveAuthorizationRequest,
    create_live_authorization,
)
from nasdaq_auto_trader.models import AccountSnapshot, Bar, Position
from tests.ai_quant_fixtures import promoted_payload, valid_spec_payload
from tests.config_engine_fixtures import compact_strategy_config


def _live_engine(
    paths,
    guard,
    broker,
    max_attempts=12,
    *,
    issue_authorization=True,
    daily_forced=False,
    market_data=None,
):
    now = datetime(2026, 7, 13, 14, 30, tzinfo=timezone.utc)
    config = AppConfig(
        mode="live",
        allow_live_trading=True,
        live_environment_authorized=True,
        symbols=["POISON"],
        broker="kis" if daily_forced else "alpaca",
        alpaca=AlpacaCredentials("key", "secret", paper=False),
        kis=KISCredentials("app", "secret", "12345678", paper=False),
        strategy=compact_strategy_config(),
    )
    if issue_authorization and guard.authorization_store.load() is None:
        authorization = create_live_authorization(
            LiveAuthorizationRequest(config, paths, now, max_attempts)
        )
        if isinstance(authorization, LiveAuthorizationBlock):
            raise AssertionError(authorization.reason)
        guard.authorization_store.issue(authorization)
    return TradingEngine(
        config,
        broker=broker,
        market_data=market_data or _LiveMarketData(),
        clock=lambda: now,
        trading_settings=TradingSettings(
            auto_symbol_selection_enabled=True,
            dry_run=False,
            live_trading=True,
            require_confirm_before_buy=False,
            require_confirm_before_sell=False,
            max_daily_buy_count=10,
            daily_forced_order_enabled=daily_forced,
            automatic_session_authorization_enabled=daily_forced,
            unattended_operation_enabled=daily_forced,
            unattended_live_trading_enabled=daily_forced,
            max_position_qty=10,
        ),
        live_order_confirmation=True,
        strategy_artifact_paths=paths,
        automatic_order_guard=guard,
    )


class _LiveMarketData:
    def get_stock_bars(self, symbols, timeframe, start, end=None, limit=1000):
        del timeframe, start, end, limit
        return {symbol: _bars(symbol) for symbol in symbols}

    def get_latest_quotes(self, symbols):
        return {symbol: {"bp": 238.99, "ap": 239.01} for symbol in symbols}

    def get_account(self, refresh=False):
        del refresh
        return AccountSnapshot(10_000, 10_000, 10_000)

    def list_positions(self, refresh=False):
        del refresh
        return {}


class _LiveSellMarketData(_LiveMarketData):
    def list_positions(self, refresh=False):
        del refresh
        return {"AAPL": Position("AAPL", 1, 239, 300)}


class _LiveBroker:
    def __init__(self, status: str) -> None:
        self.status = status
        self.orders = []

    def submit_order(self, order):
        self.orders.append(order)
        return {"status": self.status, "id": str(len(self.orders))}

    def get_overseas_buying_power(self, symbol, limit_price):
        del symbol, limit_price
        return 10_000.0


class _SecondWriteFailsAudit:
    def __init__(self) -> None:
        self.calls = 0

    def append(self, event):
        del event
        self.calls += 1
        return self.calls == 1


def _bars(symbol: str) -> list[Bar]:
    return [
        Bar(
            symbol,
            "2026-07-13T14:29:00+00:00",
            99 + index,
            101 + index,
            98 + index,
            100 + index,
            1_000_000,
        )
        for index in range(140)
    ]


def _write_champion(
    paths: StrategyArtifactPaths,
    strategy_id: str = "auto",
    threshold: float | None = None,
) -> None:
    payload = valid_spec_payload()
    payload["strategy_id"] = strategy_id
    payload["entry_rule"]["top_n"] = 1
    if threshold is not None:
        payload["entry_rule"]["threshold"] = threshold
    paths.spec_dir.mkdir(parents=True, exist_ok=True)
    (paths.spec_dir / f"{strategy_id}-v1.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    promoted = promoted_payload(strategy_id)
    paths.promoted_path.write_text(json.dumps(promoted), encoding="utf-8")
