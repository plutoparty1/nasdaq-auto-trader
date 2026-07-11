from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class ArtifactPathEscapedBaseError(ValueError):
    base: Path
    attempted_path: Path

    def __str__(self) -> str:
        return "artifact_path_escaped_base"


def safe_artifact_path(directory: Path, raw_name: str, suffix: str) -> Path:
    safe_name = SAFE_NAME_PATTERN.sub("_", raw_name).strip("._")
    if not safe_name:
        safe_name = "artifact"
    filename = f"{safe_name[:120]}{suffix}"
    base = directory.resolve()
    path = (base / filename).resolve()
    if base != path.parent:
        raise ArtifactPathEscapedBaseError(base, path)
    return path
