from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final, assert_never

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import (
    StrategyArtifactPaths,
    default_strategy_artifact_paths,
)
from nasdaq_auto_trader.ai_quant_lab.operator_commands import (
    champion_lock_payload,
    live_cycle_payload,
    nightly_payload,
    paper_shadow_payload,
    rollback_payload,
    status_payload,
)
from nasdaq_auto_trader.ai_quant_lab.operator_degradation import monitor_degradation_payload
from nasdaq_auto_trader.ai_quant_lab.operator_models import (
    OperatorCommand,
    OperatorPaths,
    UnsupportedCommandError,
)
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject

COMMAND_VALUES: Final[tuple[OperatorCommand, ...]] = (
    "status",
    "nightly",
    "champion-lock",
    "rollback",
    "monitor-degradation",
    "paper-shadow",
    "live-cycle",
)


def run_operator_command(
    command: OperatorCommand,
    args: argparse.Namespace,
    paths: OperatorPaths,
) -> JsonObject:
    match command:
        case "status":
            return status_payload(paths)
        case "nightly":
            return nightly_payload(args, paths)
        case "champion-lock":
            return champion_lock_payload(args, paths)
        case "rollback":
            return rollback_payload(args, paths)
        case "monitor-degradation":
            return monitor_degradation_payload(args, paths)
        case "paper-shadow":
            return paper_shadow_payload(args, paths)
        case "live-cycle":
            return live_cycle_payload(args, paths)
        case unreachable:
            assert_never(unreachable)


def operator_paths_from_args(args: argparse.Namespace) -> OperatorPaths:
    artifact_root = getattr(args, "artifact_root", None)
    defaults = (
        StrategyArtifactPaths.from_root(Path(artifact_root))
        if isinstance(artifact_root, str) and artifact_root.strip()
        else default_strategy_artifact_paths()
    )
    return OperatorPaths(
        optional_path(args.ai_config) or defaults.ai_config_path,
        optional_path(args.registry_path) or defaults.registry_path,
        optional_path(args.promoted_path) or defaults.promoted_path,
        optional_path(args.spec_dir) or defaults.spec_dir,
        optional_path(args.audit_log) or defaults.audit_log_path,
    )


def command_from_text(value: str) -> OperatorCommand:
    for command in COMMAND_VALUES:
        if value == command:
            return command
    raise UnsupportedCommandError(value)


def exit_code(command: OperatorCommand, payload: JsonObject) -> int:
    match command:
        case "status":
            return 0
        case "nightly" | "champion-lock" | "rollback" | "paper-shadow" | "live-cycle":
            return 0 if payload.get("status") == "completed" else 2
        case "monitor-degradation":
            return 0 if payload.get("status") in ("healthy", "rolled_back") else 2
        case unreachable:
            assert_never(unreachable)


def optional_path(value: str | None) -> Path | None:
    return Path(value) if value else None
