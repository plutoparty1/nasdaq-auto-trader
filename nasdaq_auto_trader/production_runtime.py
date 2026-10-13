"""Load the separate production draft without importing legacy account approvals."""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from .ai_quant_lab.artifact_paths import StrategyArtifactPaths
from .config import AppConfig, load_config
from .config_runtime import apply_settings_to_app_config
from .config_settings import TradingSettings
from .config_storage import load_or_create_settings
from .gui_launcher import _read_dotenv

BUILD_ID = "formal-production-20261013-r2"
STRATEGY_ID = "builtin_ai_volatility_target"
STRATEGY_VERSION = "data-b230423351524f87-catalogue-v5"
SPEC_DIGEST = "d2dd08f077a9d7d54d1771cdce798a0554737e4fd0b9ff1d866be3dba32b0729"


class ProductionRuntimeError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ProductionRuntime:
    app_dir: Path
    original_data: Path
    executable: Path
    config: AppConfig
    settings: TradingSettings
    paths: StrategyArtifactPaths

    @property
    def state_root(self) -> Path:
        return self.app_dir / "operating_state" / "NasdaqAutoTrader"

    @property
    def receipt_path(self) -> Path:
        return self.state_root / "runtime" / "production-approval.json"

    @property
    def session_path(self) -> Path:
        return self.state_root / "runtime" / "trading_session.json"

    @property
    def authorization_path(self) -> Path:
        return self.session_path.with_suffix(".live-authorization.json")

    @property
    def token_cache(self) -> Path:
        return self.original_data / "runtime" / ".kis_token.json"


def load_runtime(app_dir: Path, original_data: Path, executable: Path | None = None) -> ProductionRuntime:
    config_path, settings_path = app_dir / "config.operating.json", app_dir / "trading_config.json"
    source_path = app_dir / "credential-source.txt"
    if not all(path.is_file() for path in (config_path, settings_path, source_path)):
        raise ProductionRuntimeError("production_draft_files_missing")
    source = Path(source_path.read_text(encoding="utf-8-sig").strip())
    values = {key: value for key, value in os.environ.items() if key.startswith("KIS_")}
    for path in (original_data / ".env", source.parent / ".env"):
        for key, value in _read_dotenv(path).items():
            if key.startswith("KIS_"):
                values.setdefault(key, value)
    credentials = load_config(source, environ=values).kis
    base = load_config(config_path, environ={})
    requested = load_or_create_settings(settings_path)
    settings = replace(requested, live_trading=True, dry_run=False,
                       auto_symbol_selection_enabled=True,
                       daily_minimum_buy_enabled=False, daily_forced_order_enabled=False,
                       automatic_session_authorization_enabled=False,
                       unattended_operation_enabled=False, unattended_live_trading_enabled=False,
                       order_qty=1, max_position_qty=1, allow_additional_buy=False,
                       ai_order_qty_enabled=False, ai_trade_decision_enabled=False)
    base = replace(base, broker="kis", mode="live", allow_live_trading=True,
                   live_environment_authorized=True,
                   kis=replace(base.kis, app_key=credentials.app_key,
                               app_secret=credentials.app_secret,
                               account_no=credentials.account_no,
                               account_product_code=credentials.account_product_code, paper=False),
                   trading_agents=replace(base.trading_agents, enabled=False))
    config = apply_settings_to_app_config(base, settings)
    root = app_dir / "operating_state" / "NasdaqAutoTrader"
    return ProductionRuntime(app_dir, original_data, executable or Path(sys.executable).resolve(),
                             config, settings, StrategyArtifactPaths.from_root(root / "ai_quant_lab"))


def isolate_runtime(runtime: ProductionRuntime) -> None:
    # Existing app-data APIs use a process-local root; original approvals stay outside it.
    os.environ["LOCALAPPDATA"] = str(runtime.state_root.parent)


def source_digest(runtime: ProductionRuntime) -> str:
    digest = hashlib.sha256()
    for path in (runtime.app_dir / "config.operating.json", runtime.app_dir / "trading_config.json",
                 runtime.app_dir / "fee-review.json", runtime.app_dir / "credential-source.txt",
                 runtime.paths.registry_path, runtime.paths.promoted_path,
                 runtime.paths.ai_config_path):
        if path is