from __future__ import annotations

import os
from importlib import resources
from pathlib import Path
from typing import Mapping


APP_DATA_DIR = "NasdaqAutoTrader"


class ResourceLoadError(RuntimeError):
    def __init__(self, reason: str, resource_name: str) -> None:
        self.reason = reason
        self.resource_name = resource_name
        super().__init__(f"{reason}: {resource_name}")


def read_quant_resource(relative_name: str) -> str:
    try:
        target = resources.files("nasdaq_auto_trader.quant_data").joinpath(relative_name)
        return target.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        raise ResourceLoadError("universe_resource_missing", relative_name) from exc


def application_data_root(
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    values = os.environ if environ is None else environ
    local_app_data = values.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / APP_DATA_DIR
    xdg_data_home = values.get("XDG_DATA_HOME", "").strip()
    if xdg_data_home:
        return Path(xdg_data_home) / APP_DATA_DIR
    return (home or Path.home()) / ".local" / "share" / APP_DATA_DIR
