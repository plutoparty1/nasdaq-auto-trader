"""Start the isolated, order-locked repaired release without live CLI routes."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, Literal

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import StrategyArtifactPaths
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from nasdaq_auto_trader.config import AppConfig, load_config
from nasdaq_auto_trader.config_runtime import apply_settings_to_app_config
from nasdaq_auto_trader.config_settings import TradingSettings
from nasdaq_auto_trader.config_storage import load_or_create_settings
from nasdaq_auto_trader.quant_data.symbol_selector import (
    ResolvedStrategy,
    resolve_strategy,
)
from nasdaq_auto_trader.safe_runtime import (
    BUILD_ID,
    enable,
    sanitize_config,
    sanitize_settings,
)
from nasdaq_auto_trader.single_instance import SingleInstanceGuard

EXPECTED_SPEC_DIGEST: Final = "d2dd08f077a9d7d54d1771cdce798a0554737e4fd0b9ff1d866be3dba32b0729"


@dataclass(frozen=True, slots=True)
class EffectiveRuntime:
    config: AppConfig
    settings: TradingSettings
    requested_config: AppConfig
    requested_settings: TradingSettings


def load_effective_runtime(app_dir: Path) -> EffectiveRuntime:
    config_path = app_dir / "config.safe.json"
    settings_path = app_dir / "trading_config.json"
    if not config_path.is_file() or not settings_path.is_file():
        raise RuntimeError("safe_release_config_missing")
    if (app_dir / ".env").exists():
        raise RuntimeError("safe_release_dotenv_forbidden")
    requested_config = load_config(config_path, environ={})
    requested_settings = load_or_create_settings(settings_path)
    settings = sanitize_settings(requested_settings)
    config = sanitize_config(apply_settings_to_app_config(requested_config, settings))
    return EffectiveRuntime(config, settings, requested_config, requested_settings)


def settings_flags(settings: TradingSettings) -> JsonObject:
    return {
        "live_trading": settings.live_trading, "dry_run": settings.dry_run,
        "daily_minimum_buy_enabled": settings.daily_minimum_buy_enabled,
        "daily_forced_order_enabled": settings.daily_forced_order_enabled,
        "unattended_live_trading_enabled": settings.unattended_live_trading_enabled,
        "automatic_session_authorization_enabled": settings.automatic_session_authorization_enabled,
    }


def parse_action(argv: list[str]) -> tuple[Literal["gui", "check", "replay"], Path | None]:
    """Accept only simulation actions; unknown and live arguments fail closed."""
    if not argv:
        return "gui", None
    if argv == ["--runtime-check"]:
        return "check", None
    if len(argv) == 2 and argv[0] == "--replay" and not argv[1].startswith("--"):
        return "replay", Path(argv[1]).resolve()
    raise SystemExit("blocked: only --runtime-check or --replay OUTPUT is allowed")


def isolate_runtime(app_dir: Path) -> Path:
    """Scope app-data redirection to this process and this separate release."""
    runtime = app_dir / "simulation" / "NasdaqAutoTrader"
    runtime.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALAPPDATA"] = str(runtime.parent)
    return runtime


def prepare_runtime(app_dir: Path) -> JsonObject:
    """Validate the real runtime strategy and record loaded safe-release identity."""
    enable()
    runtime = isolate_runtime(app_dir)
    effective = load_effective_runtime(app_dir)
    paths = StrategyArtifactPaths.from_root(runtime / "ai_quant_lab")
    resolved = resolve_strategy("dry_run", paths)
    if not isinstance(resolved, ResolvedStrategy):
        raise RuntimeError(f"safe_release_strategy_blocked:{resolved.reason}")
    if (resolved.spec.strategy_id != "builtin_ai_volatility_target"
            or resolved.spec.version != "data-b230423351524f87-catalogue-v5"
            or resolved.spec_digest != EXPECTED_SPEC_DIGEST):
        raise RuntimeError("safe_release_strategy_identity_mismatch")
    payload: JsonObject = {
        "build_id": BUILD_ID, "mode": "dry_run", "order_lock": True,
        "live_transition": "simulation_only_requires_separate_approved_production_release",
        "strategy_id": resolved.spec.strategy_id,
        "strategy_version": resolved.spec.version,
        "strategy_digest": resolved.spec_digest,
        "config_source": str(app_dir / "config.safe.json"),
        "config_source_sha256": hashlib.sha256((app_dir / "config.safe.json").read_bytes()).hexdigest(),
        "settings_source": str(app_dir / "trading_config.json"),
        "settings_source_sha256": hashlib.sha256((app_dir / "trading_config.json").read_bytes()).hexdigest(),
        "requested_config_mode": effective.requested_config.mode,
        "requested_allow_live_trading": effective.requested_config.allow_live_trading,
        "effective_allow_live_trading": effective.config.allow_live_trading,
        "effective_live_environment_authorized": effective.config.live_environment_authorized,
        "requested_settings": settings_flags(effective.requested_settings),
        "effective_settings": settings_flags(effective.settings),
        "effective_risk_per_trade_pct": effective.config.risk.risk_per_trade_pct,
        "effective_initial_stop_loss_pct": effective.config.strategy.stop_loss_pct,
        "effective_estimated_roundtrip_cost_pct": effective.config.risk.estimated_roundtrip_cost_pct,
        "estimated_cost_source": "release_assumption_not_actual_broker_fees",
        "effective_strategy_config_sha256": hashlib.sha256(json.dumps(asdict(effective.config.strategy), sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "policy_source": "safe_runtime:irreversible_simulation_policy",
        "app_data_source": str(runtime),
        "registry_source": str(paths.registry_path),
        "entry_policy": "no_minimum_buy_bypass;signal_conflict_guard;planned_loss_budget;completed_bar_dedup",
    }
    output = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    (runtime / "startup.json").write_text(output + "\n", encoding="utf-8")
    print("SAFE_RELEASE " + output, flush=True)
    return payload


def main(argv: list[str] | None = None) -> int:
    """Run only the isolated simulation GUI or its offline verification surface."""
    enable()
    action, output = parse_action(sys.argv[1:] if argv is None else argv)
    app_dir = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
               else Path(__file__).resolve().parents[1])
    prepare_runtime(app_dir)
    if action == "check":
        return 0
    if action == "replay":
        from nasdaq_auto_trader.roundtrip_replay import run_replay
        if output is None:
            raise RuntimeError("safe_release_replay_output_missing")
        run_replay(output, app_dir)
        return 0
    from nasdaq_auto_trader.app_ui import launch_gui
    config = load_effective_runtime(app_dir).config
    guard = SingleInstanceGuard(app_dir / "simulation" / "safe-gui.lock")
    if not guard.acquire():
        raise RuntimeError("safe_release_duplicate_instance_blocked")
    try:
        launch_gui(config, config_path=app_dir / "config.safe.json",
                   settings_path=app_dir / "trading_config.json", start_paused=True)
    finally:
        guard.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
