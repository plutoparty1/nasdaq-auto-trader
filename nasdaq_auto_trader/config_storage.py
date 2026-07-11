from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config_settings import (
    SettingsLoadError,
    SettingsValidationError,
    SettingsValueError,
    TradingSettings,
)
from .config_validation import _normalized_tickers, validate_settings


DEFAULT_SETTINGS_FILE = "trading_config.json"

def default_settings_path(base_dir: str | Path | None = None) -> Path:
    """Return the default GUI settings path."""

    return Path(base_dir or Path.cwd()) / DEFAULT_SETTINGS_FILE


def load_or_create_settings(path: str | Path | None = None) -> TradingSettings:
    """Load settings, creating a default JSON file when missing."""

    settings_path = Path(path) if path is not None else default_settings_path()
    if not settings_path.exists():
        settings = TradingSettings()
        save_settings(settings, settings_path)
        return settings
    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SettingsLoadError(
            f"settings JSON parse failed: {settings_path}: {exc}"
        ) from exc
    except OSError as exc:
        raise SettingsLoadError(f"settings file read failed: {settings_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SettingsLoadError(f"settings file must contain a JSON object: {settings_path}")

    try:
        settings = settings_from_dict(raw)
    except (TypeError, ValueError) as exc:
        raise SettingsLoadError(f"settings value parse failed: {settings_path}: {exc}") from exc
    result = validate_settings(settings)
    if not result.ok:
        raise SettingsValidationError(result.errors, result.warnings)
    return settings


def save_settings(settings: TradingSettings, path: str | Path | None = None) -> None:
    """Validate and save settings as JSON."""

    result = validate_settings(settings)
    if not result.ok:
        raise SettingsValidationError(result.errors, result.warnings)

    settings_path = Path(path) if path is not None else default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def settings_from_dict(raw: dict[str, Any]) -> TradingSettings:
    """Build settings from a partial dictionary, using defaults for blanks."""

    defaults = TradingSettings()
    values = defaults.to_dict()
    for key, value in raw.items():
        if key not in values:
            continue
        default = values[key]
        values[key] = _coerce_setting_value(value, default)
    return TradingSettings(**values)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "1", "yes", "y", "on"):
            return True
        if text in ("false", "0", "no", "n", "off"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    raise SettingsValueError(f"invalid boolean value: {value!r}")


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        raise SettingsValueError(f"invalid integer value: {value!r}")
    number = int(value)
    if float(value) != number:
        raise SettingsValueError(f"invalid integer value: {value!r}")
    return number


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        raise SettingsValueError(f"invalid number value: {value!r}")
    return float(value)


def _coerce_setting_value(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(default, bool):
        return _as_bool(value)
    if isinstance(default, int) and not isinstance(default, bool):
        return _as_int(value)
    if isinstance(default, float):
        return _as_float(value)
    if isinstance(default, str):
        return str(value).strip()
    if isinstance(default, list):
        return _as_ticker_list(value)
    return value


def _as_ticker_list(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise SettingsValueError(
                    f"invalid ticker list value: {value!r}"
                ) from exc
            return _as_ticker_list(parsed)
        return _normalized_tickers(stripped.replace("\n", ",").split(","))
    if isinstance(value, list):
        return _normalized_tickers([str(item) for item in value])
    raise SettingsValueError(f"invalid ticker list value: {value!r}")
