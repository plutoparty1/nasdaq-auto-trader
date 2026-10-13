"""Read configured KIS credentials without importing the live application."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .research_readonly import Credentials, ResearchError


def load_credentials(config_path: Path) -> Credentials:
    raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
    kis = raw.get("kis", {})
    if raw.get("broker") != "kis" or kis.get("paper") is not False:
        raise ResearchError("configured_broker_or_account_mode_mismatch")
    values = dict(os.environ)
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "NasdaqAutoTrader" / ".env",
        config_path.parent / ".env",
        config_path.parent.parent / ".env",
    ]
    for dotenv in dict.fromkeys(candidates):
        if not dotenv.exists():
            continue
        file_values: dict[str, str] = {}
        for line in dotenv.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key, separator, value = stripped.removeprefix("export ").partition("=")
            if separator:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                file_values[key.strip()] = value
        for key, value in file_values.items():
            values.setdefault(key, value)

    def pick(name: str, key: str, default: str = "") -> str:
        value = values.get(name, kis.get(key, default))
        return value if isinstance(value, str) else ""

    result = Credentials(
        pick("KIS_APP_KEY", "app_key"),
        pick("KIS_APP_SECRET", "app_secret"),
        pick("KIS_ACCOUNT_NO", "account_no"),
        pick("KIS_ACCOUNT_PRODUCT_CODE", "account_product_code", "01"),
    )
    if not all((result.app_key, result.app_secret, result.account, result.product)):
        raise ResearchError("configured_credentials_missing")
    return result


def private_output_root(repo: Path) -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise ResearchError("private_storage_unavailable")
    path = (
        Path(local) / "NasdaqAutoTrader" / "research" / "entry-policy-20260929"
    ).resolve()
    if path.is_relative_to(repo.resolve()):
        raise ResearchError("private_storage_inside_repository")
    return path
