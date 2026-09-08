from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .ai_quant_lab.artifact_paths import (
    StrategyArtifactPaths,
    default_strategy_artifact_paths,
)
from .ai_quant_lab.registry import StrategyRegistry
from .ai_quant_lab.registry_models import StrategyStatus
from .automatic_selection import AutomaticSelectionRequest, prepare_automatic_selection
from .cli_formatters import selection_report_to_dict
from .cli_types import JsonObject
from .config import AppConfig
from .quant_data.diagnostic_market_data import (
    DiagnosticFixtureError,
    DiagnosticMarketData,
)
from .quant_data.symbol_selector import (
    StrategyResolutionBlock,
    blocked_selection_report,
    resolve_strategy,
)
from .quant_data.universe_snapshot import load_default_universe


PRIVATE_FIXTURE_NAMES = frozenset(
    {
        ".env",
        ".kis_token.json",
        "audit.jsonl",
        "promoted_strategy.json",
        "selection_cache.json",
        "trading_session.json",
    }
)
LIVE_STATUSES = frozenset({StrategyStatus.SHADOW_LIVE, StrategyStatus.CHAMPION})


class DiagnosticUsageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DiagnosticRequest:
    output_path: Path
    fixture_root: Path | None = None


def parse_diagnostic_request(argv: list[str]) -> DiagnosticRequest | None:
    has_diagnostic = any(item.startswith("--diagnostic-") for item in argv)
    if not has_diagnostic:
        return None
    values: dict[str, Path] = {}
    index = 0
    while index < len(argv):
        option = argv[index]
        if option not in ("--diagnostic-output", "--diagnostic-fixture-root"):
            raise DiagnosticUsageError("diagnostic_options_wrong_surface")
        if option in values or index + 1 >= len(argv):
            raise DiagnosticUsageError("diagnostic_options_invalid")
        values[option] = Path(argv[index + 1])
        index += 2
    output = values.get("--diagnostic-output")
    if output is None:
        raise DiagnosticUsageError("diagnostic_output_required")
    return DiagnosticRequest(output, values.get("--diagnostic-fixture-root"))


def run_frozen_diagnostic(
    output_path: Path,
    fixture_root: Path | None = None,
) -> int:
    if fixture_root is not None and output_path.resolve().is_relative_to(
        fixture_root.resolve()
    ):
        raise DiagnosticUsageError("diagnostic_output_inside_fixture_forbidden")
    try:
        selection = _selection_payload(fixture_root)
        payload = {
            "diagnostic_status": "complete",
            "resource_loaded": True,
            "artifact_source": "fixture" if fixture_root is not None else "application_data",
            "selection": selection,
            "submitted_order": False,
            "network_client_constructed": False,
        }
        exit_code = 0
    except DiagnosticFixtureError as exc:
        payload = {
            "diagnostic_status": "blocked",
            "reason": exc.reason,
            "submitted_order": False,
            "network_client_constructed": False,
        }
        exit_code = 2
    _write_output(output_path, payload)
    return exit_code


def _selection_payload(fixture_root: Path | None) -> JsonObject:
    snapshot = load_default_universe()
    if fixture_root is None:
        paths = default_strategy_artifact_paths()
        resolution = resolve_strategy("paper", paths)
        if isinstance(resolution, StrategyResolutionBlock):
            report = blocked_selection_report(snapshot, resolution.reason)
        else:
            report = blocked_selection_report(
                snapshot,
                "diagnostic_fixture_required_for_market_data",
                resolution,
            )
        return selection_report_to_dict(report)
    paths = _validated_fixture_paths(fixture_root)
    market_data = DiagnosticMarketData.from_file(fixture_root / "bars.json")
    result = prepare_automatic_selection(
        AutomaticSelectionRequest(
            AppConfig(mode="dry_run", symbols=[]),
            market_data,
            paths,
            market_data.as_of,
        )
    )
    return selection_report_to_dict(result.report)


def _validated_fixture_paths(root: Path) -> StrategyArtifactPaths:
    if not root.is_dir():
        raise DiagnosticFixtureError("diagnostic_fixture_invalid")
    names = {path.name for path in root.rglob("*") if path.is_file()}
    if names & PRIVATE_FIXTURE_NAMES:
        reason = (
            "diagnostic_live_artifacts_forbidden"
            if "promoted_strategy.json" in names
            else "diagnostic_private_artifacts_forbidden"
        )
        raise DiagnosticFixtureError(reason)
    paths = StrategyArtifactPaths.from_root(root)
    records = StrategyRegistry(paths.registry_path, paths.promoted_path).load_records()
    if any(
        record.allowed_for_live
        or record.manual_approval
        or record.status in LIVE_STATUSES
        for record in records
    ):
        raise DiagnosticFixtureError("diagnostic_live_artifacts_forbidden")
    return paths


def _write_output(path: Path, payload: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
