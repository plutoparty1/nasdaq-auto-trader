"""Load runtime configuration from JSON, .env, and environment variables."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping, TypeVar, get_type_hints

from .broker import AlpacaCredentials, KISCredentials
from .config_errors import ConfigLoadError, TradingModeValidationError
from .config_types import (
    AlpacaConfigDict,
    AppConfigDict,
    BrokerName,
    KISConfigDict,
    RunMode,
)
from .risk import RiskConfig
from .strategy import StrategyConfig
from .trading_agents import TradingAgentsConfig


ConfigDataclass = TypeVar("ConfigDataclass")


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Complete application settings."""

    mode: RunMode = "dry_run"
    broker: BrokerName = "alpaca"
    symbols: list[str] = field(default_factory=lambda: ["QQQ"])
    timeframe: str = "1Day"
    lookback_days: int = 260
    bar_limit: int = 1000
    allow_live_trading: bool = False
    live_environment_authorized: bool = False
    regular_market_hours_only: bool = True
    alpaca: AlpacaCredentials = field(
        default_factory=lambda: AlpacaCredentials("", "", True)
    )
    kis: KISCredentials = field(
        default_factory=lambda: KISCredentials("", "", "", paper=True)
    )
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    trading_agents: TradingAgentsConfig = field(default_factory=TradingAgentsConfig)

    def to_dict(self) -> AppConfigDict:
        """Return display-safe configuration with credentials masked."""

        alpaca: AlpacaConfigDict = {
            "api_key": "***" if self.alpaca.api_key else "",
            "secret_key": "***" if self.alpaca.secret_key else "",
            "paper": self.alpaca.paper,
            "feed": self.alpaca.feed,
            "timeout": self.alpaca.timeout,
        }
        kis: KISConfigDict = {
            "app_key": "***" if self.kis.app_key else "",
            "app_secret": "***" if self.kis.app_secret else "",
            "account_no": "***" if self.kis.account_no else "",
            "account_product_code": self.kis.account_product_code,
            "paper": self.kis.paper,
            "order_exchange_code": self.kis.order_exchange_code,
            "price_exchange_code": self.kis.price_exchange_code,
            "currency": self.kis.currency,
            "timeout": self.kis.timeout,
        }
        return {
            "mode": self.mode,
            "broker": self.broker,
            "symbols": list(self.symbols),
            "timeframe": self.timeframe,
            "lookback_days": self.lookback_days,
            "bar_limit": self.bar_limit,
            "allow_live_trading": self.allow_live_trading,
            "live_environment_authorized": self.live_environment_authorized,
            "regular_market_hours_only": self.regular_market_hours_only,
            "alpaca": alpaca,
            "kis": kis,
            "strategy": asdict(self.strategy),
            "risk": asdict(self.risk),
            "trading_agents": asdict(self.trading_agents),
        }


def load_config(
    path: str | Path | None = None,
    environ: dict[str, str] | None = None,
) -> AppConfig:
    """Load JSON config and let .env plus environment variables override credentials."""

    config_path = Path(path) if path is not None else None
    env = _effective_env(config_path, environ)
    raw: dict[str, Any] = {}
    if config_path is not None:
        try:
            with config_path.open("r", encoding="utf-8-sig") as file:
                loaded = json.load(file)
        except json.JSONDecodeError as exc:
            raise ConfigLoadError(config_path, str(exc)) from exc
        except OSError as exc:
            raise ConfigLoadError(config_path, str(exc)) from exc
        if not isinstance(loaded, dict):
            raise ConfigLoadError(config_path, "top-level JSON value must be an object")
        raw = loaded

    mode = raw.get("mode", "dry_run")
    symbols = raw.get("symbols", ["QQQ"])
    error_path = config_path or Path("<defaults>")
    alpaca_raw = _config_section(raw, "alpaca", error_path)
    paper = _bool_from_config(alpaca_raw.get("paper"), mode != "live")
    credentials = AlpacaCredentials(
        api_key=env.get("ALPACA_API_KEY", alpaca_raw.get("api_key", "")),
        secret_key=env.get("ALPACA_SECRET_KEY", alpaca_raw.get("secret_key", "")),
        paper=paper,
        feed=alpaca_raw.get("feed", env.get("ALPACA_DATA_FEED", "iex")),
        timeout=int(alpaca_raw.get("timeout", 30)),
    )
    kis_raw = _config_section(raw, "kis", error_path)
    kis_paper = _bool_from_config(kis_raw.get("paper"), mode != "live")
    kis_credentials = KISCredentials(
        app_key=env.get("KIS_APP_KEY", kis_raw.get("app_key", "")),
        app_secret=env.get("KIS_APP_SECRET", kis_raw.get("app_secret", "")),
        account_no=env.get("KIS_ACCOUNT_NO", kis_raw.get("account_no", "")),
        account_product_code=env.get(
            "KIS_ACCOUNT_PRODUCT_CODE",
            kis_raw.get("account_product_code", "01"),
        ),
        paper=kis_paper,
        order_exchange_code=env.get(
            "KIS_ORDER_EXCHANGE_CODE",
            kis_raw.get("order_exchange_code", "NASD"),
        ),
        price_exchange_code=env.get(
            "KIS_PRICE_EXCHANGE_CODE",
            kis_raw.get("price_exchange_code", "NAS"),
        ),
        currency=env.get("KIS_CURRENCY", kis_raw.get("currency", "USD")),
        timeout=int(kis_raw.get("timeout", 30)),
    )

    strategy_raw = _config_section(raw, "strategy", error_path)
    risk_raw = _config_section(raw, "risk", error_path)
    trading_agents_raw = _config_section(raw, "trading_agents", error_path)

    return AppConfig(
        mode=mode,
        broker=raw.get("broker", "alpaca"),
        symbols=[str(symbol).upper() for symbol in symbols],
        timeframe=str(raw.get("timeframe", "1Day")),
        lookback_days=int(raw.get("lookback_days", 260)),
        bar_limit=int(raw.get("bar_limit", 1000)),
        allow_live_trading=_bool_from_config(raw.get("allow_live_trading"), False),
        live_environment_authorized=(
            env.get("NASDAQ_AUTO_TRADER_ALLOW_LIVE", "") == "YES"
        ),
        regular_market_hours_only=_bool_from_config(
            raw.get("regular_market_hours_only"),
            True,
        ),
        alpaca=credentials,
        kis=kis_credentials,
        strategy=_dataclass_from_dict(StrategyConfig, strategy_raw),
        risk=_dataclass_from_dict(RiskConfig, risk_raw),
        trading_agents=_dataclass_from_dict(
            TradingAgentsConfig,
            trading_agents_raw,
        ),
    )


def _config_section(raw: Mapping[str, Any], key: str, path: Path) -> Mapping[str, Any]:
    value = raw.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigLoadError(path, f"{key} section must be an object")
    return value


def _bool_from_config(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _effective_env(
    config_path: Path | None,
    environ: dict[str, str] | None,
) -> dict[str, str]:
    """Return .env values with real environment variables taking precedence."""

    dotenv_path = (
        config_path.parent / ".env" if config_path is not None else Path.cwd() / ".env"
    )
    env = _load_dotenv(dotenv_path)
    env.update(dict(os.environ if environ is None else environ))
    return env


def _load_dotenv(path: Path) -> dict[str, str]:
    """Parse simple KEY=VALUE lines from a local .env file."""

    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()

        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        key = key.strip()
        if not key:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def validate_trading_mode(config: AppConfig) -> None:
    """Block live-capable modes unless credentials and explicit flags exist."""

    if config.mode not in ("dry_run", "paper", "live"):
        raise TradingModeValidationError("mode must be one of dry_run, paper, live")
    if config.broker not in ("alpaca", "kis"):
        raise TradingModeValidationError("broker must be one of alpaca, kis")
    if config.mode == "live" and not config.allow_live_trading:
        raise TradingModeValidationError("live trading requires allow_live_trading=true")
    if config.mode == "live" and not config.live_environment_authorized:
        raise TradingModeValidationError(
            "live trading requires environment authorization"
        )
    if config.mode in ("paper", "live"):
        if config.broker == "alpaca" and (
            not config.alpaca.api_key or not config.alpaca.secret_key
        ):
            raise TradingModeValidationError(
                "paper/live mode requires ALPACA_API_KEY and ALPACA_SECRET_KEY"
            )
        if config.broker == "kis" and (
            not config.kis.app_key
            or not config.kis.app_secret
            or not config.kis.account_no
        ):
            raise TradingModeValidationError(
                "paper/live mode with broker=kis requires KIS_APP_KEY, "
                "KIS_APP_SECRET, and KIS_ACCOUNT_NO"
            )


def _dataclass_from_dict(
    cls: type[ConfigDataclass],
    values: Mapping[str, Any],
) -> ConfigDataclass:
    """Ignore unknown keys while constructing nested dataclass config."""

    allowed = {field.name for field in fields(cls)}
    type_hints = get_type_hints(cls)
    filtered = {}
    for key, value in values.items():
        if key not in allowed:
            continue
        if type_hints.get(key) is bool and not isinstance(value, bool):
            continue
        filtered[key] = value
    return cls(**filtered)
