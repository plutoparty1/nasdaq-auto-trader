from __future__ import annotations

from typing import Any, Literal, TypedDict


RunMode = Literal["dry_run", "paper", "live"]
BrokerName = Literal["alpaca", "kis"]


class AlpacaConfigDict(TypedDict):
    api_key: str
    secret_key: str
    paper: bool
    feed: str
    timeout: int


class KISConfigDict(TypedDict):
    app_key: str
    app_secret: str
    account_no: str
    account_product_code: str
    paper: bool
    order_exchange_code: str
    price_exchange_code: str
    currency: str
    timeout: int


class AppConfigDict(TypedDict):
    mode: RunMode
    broker: BrokerName
    symbols: list[str]
    timeframe: str
    lookback_days: int
    bar_limit: int
    allow_live_trading: bool
    live_environment_authorized: bool
    regular_market_hours_only: bool
    alpaca: AlpacaConfigDict
    kis: KISConfigDict
    strategy: dict[str, Any]
    risk: dict[str, Any]
    trading_agents: dict[str, Any]
