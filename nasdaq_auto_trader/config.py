"""JSON 설정과 환경변수를 읽어 실행 설정을 만든다."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Literal

from .broker import AlpacaCredentials
from .risk import RiskConfig
from .strategy import StrategyConfig


RunMode = Literal["dry_run", "paper", "live"]


@dataclass(frozen=True)
class AppConfig:
    """자동매매 전체 실행 설정을 담는다."""

    mode: RunMode = "dry_run"
    symbols: list[str] = field(default_factory=lambda: ["QQQ"])
    timeframe: str = "1Day"
    lookback_days: int = 260
    bar_limit: int = 1000
    allow_live_trading: bool = False
    alpaca: AlpacaCredentials = field(
        default_factory=lambda: AlpacaCredentials("", "", True)
    )
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    def to_dict(self) -> dict:
        """화면에 보여주기 쉬운 딕셔너리로 바꾼다."""

        data = asdict(self)
        if data["alpaca"]["secret_key"]:
            data["alpaca"]["secret_key"] = "***"
        if data["alpaca"]["api_key"]:
            data["alpaca"]["api_key"] = "***"
        return data


def load_config(path: str | Path | None = None, environ: dict[str, str] | None = None) -> AppConfig:
    """설정 파일을 읽고 환경변수 값을 덮어쓴다."""

    env = environ or os.environ
    raw: dict[str, Any] = {}
    if path is not None:
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as file:
            raw = json.load(file)

    mode = raw.get("mode", "dry_run")
    symbols = raw.get("symbols", ["QQQ"])
    alpaca_raw = raw.get("alpaca", {})
    paper = bool(alpaca_raw.get("paper", mode != "live"))
    credentials = AlpacaCredentials(
        api_key=env.get("ALPACA_API_KEY", alpaca_raw.get("api_key", "")),
        secret_key=env.get("ALPACA_SECRET_KEY", alpaca_raw.get("secret_key", "")),
        paper=paper,
        feed=alpaca_raw.get("feed", env.get("ALPACA_DATA_FEED", "iex")),
        timeout=int(alpaca_raw.get("timeout", 30)),
    )

    return AppConfig(
        mode=mode,
        symbols=[str(symbol).upper() for symbol in symbols],
        timeframe=str(raw.get("timeframe", "1Day")),
        lookback_days=int(raw.get("lookback_days", 260)),
        bar_limit=int(raw.get("bar_limit", 1000)),
        allow_live_trading=bool(raw.get("allow_live_trading", False)),
        alpaca=credentials,
        strategy=_dataclass_from_dict(StrategyConfig, raw.get("strategy", {})),
        risk=_dataclass_from_dict(RiskConfig, raw.get("risk", {})),
    )


def validate_trading_mode(config: AppConfig) -> None:
    """실제 주문이 나갈 수 있는 모드에서 안전장치를 확인한다."""

    if config.mode not in ("dry_run", "paper", "live"):
        raise ValueError("mode must be one of dry_run, paper, live")
    if config.mode == "live" and not config.allow_live_trading:
        raise ValueError("live trading requires allow_live_trading=true")
    if config.mode in ("paper", "live"):
        if not config.alpaca.api_key or not config.alpaca.secret_key:
            raise ValueError("paper/live mode requires ALPACA_API_KEY and ALPACA_SECRET_KEY")


def _dataclass_from_dict(cls, values: dict[str, Any]):
    """알 수 없는 설정 키는 버리고 dataclass가 아는 키만 사용한다."""

    allowed = {field.name for field in fields(cls)}
    filtered = {key: value for key, value in values.items() if key in allowed}
    return cls(**filtered)
