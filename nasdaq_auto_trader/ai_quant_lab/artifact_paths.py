from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nasdaq_auto_trader.quant_data.resources import application_data_root


@dataclass(frozen=True, slots=True)
class StrategyArtifactPaths:
    root: Path
    registry_path: Path
    promoted_path: Path
    spec_dir: Path
    audit_log_path: Path
    ai_config_path: Path | None = None

    @classmethod
    def from_root(cls, root: Path) -> StrategyArtifactPaths:
        return cls(
            root=root,
            registry_path=root / "strategy_registry.json",
            promoted_path=root / "promoted_strategy.json",
            spec_dir=root / "strategy_specs",
            audit_log_path=root / "audit.jsonl",
            ai_config_path=root / "ai_quant_config.json",
        )


def default_strategy_artifact_paths() -> StrategyArtifactPaths:
    return StrategyArtifactPaths.from_root(application_data_root() / "ai_quant_lab")
