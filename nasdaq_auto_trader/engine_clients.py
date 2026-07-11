from __future__ import annotations

from nasdaq_auto_trader.broker import AlpacaClient, AlpacaCredentials, KISClient, KISCredentials
from nasdaq_auto_trader.config import AppConfig


def build_default_client(config: AppConfig) -> AlpacaClient | KISClient:
    if config.broker == "kis":
        kis_paper = (
            True
            if config.mode == "paper"
            else False
            if config.mode == "live"
            else config.kis.paper
        )
        credentials = KISCredentials(
            config.kis.app_key,
            config.kis.app_secret,
            config.kis.account_no,
            account_product_code=config.kis.account_product_code,
            paper=kis_paper,
            order_exchange_code=config.kis.order_exchange_code,
            price_exchange_code=config.kis.price_exchange_code,
            currency=config.kis.currency,
            timeout=config.kis.timeout,
        )
        return KISClient(credentials)
    credentials = AlpacaCredentials(
        config.alpaca.api_key,
        config.alpaca.secret_key,
        paper=config.mode != "live",
        feed=config.alpaca.feed,
        timeout=config.alpaca.timeout,
    )
    return AlpacaClient(credentials)


def use_offline_dry_run_data(config: AppConfig) -> bool:
    if config.mode != "dry_run":
        return False
    if config.broker == "kis":
        return (
            not config.kis.app_key
            or not config.kis.app_secret
            or not config.kis.account_no
        )
    return not config.alpaca.api_key or not config.alpaca.secret_key
