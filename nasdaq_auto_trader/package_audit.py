from __future__ import annotations

import json
import sys
from pathlib import Path


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


def find_private_package_artifacts(root: Path) -> tuple[Path, ...]:
    if not root.exists():
        return ()
    return tuple(
        path
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and (
            path.name in PRIVATE_NAMES
            or "strategy_specs" in path.parts
            or "auto_selection" in path.parts
            or "logs" in path.parts
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
