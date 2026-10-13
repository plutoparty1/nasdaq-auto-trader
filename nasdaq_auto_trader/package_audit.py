from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Final

from .ai_quant_lab.types import JsonValue


PRIVATE_NAMES = frozenset(
    {
        ".env",
        ".kis_token.json",
        "ai_quant_config.json",
        "audit.jsonl",
        "promoted_strategy.json",
        "selection_cache.json",
        "strategy_registry.json",
        "trading_config.json",
        "trading_session.json",
    }
)

PRIVATE_CONFIG_KEYS: Final = frozenset(
    {"app_key", "app_secret", "account_no", "api_key", "secret_key", "access_token"}
)


def _contains_private_value(value: JsonValue) -> bool:
    if isinstance(value, dict):
        return any(
            (key.lower() in PRIVATE_CONFIG_KEYS and item not in ("", None))
            or _contains_private_value(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_private_value(item) for item in value)
    return False


def _unsafe_config(path: Path) -> bool:
    if not path.name.startswith("config") or path.suffix.lower() != ".json":
        return False
    try:
        payload: JsonValue = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError):
        return True
    return not isinstance(payload, dict) or _contains_private_value(payload)


def find_private_package_artifacts(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        return (root,)
    return tuple(
        path
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and (
            path.name in PRIVATE_NAMES
            or "strategy_specs" in path.parts
            or "auto_selection" in path.parts
            or "logs" in path.parts
            or _unsafe_config(path)
        )
    )


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        return 2
    findings = find_private_package_artifacts(Path(arguments[0]))
    print(json.dumps([str(path) for path in findings], ensure_ascii=False))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
