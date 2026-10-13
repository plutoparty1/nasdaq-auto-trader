import json
from pathlib import Path

import pytest

from nasdaq_auto_trader.package_audit import find_private_package_artifacts, main


@pytest.mark.parametrize("field", ["app_key", "app_secret", "account_no", "api_key", "secret_key"])
def test_package_audit_rejects_inline_broker_credentials(tmp_path: Path, field: str) -> None:
    config = tmp_path / "config.kis.json"
    config.write_text(json.dumps({"kis": {field: "synthetic-private-value"}}), encoding="utf-8")

    assert find_private_package_artifacts(tmp_path) == (config,)


def test_package_audit_accepts_blank_broker_template(tmp_path: Path) -> None:
    config = tmp_path / "config.kis.json"
    config.write_text(json.dumps({"kis": {"app_key": "", "account_no": ""}}), encoding="utf-8")

    assert find_private_package_artifacts(tmp_path) == ()


def test_package_audit_rejects_unreadable_json_config(tmp_path: Path) -> None:
    config = tmp_path / "config.kis.json"
    config.write_text("{invalid", encoding="utf-8")

    assert find_private_package_artifacts(tmp_path) == (config,)


def test_package_audit_missing_directory_cannot_pass(tmp_path: Path) -> None:
    assert main([str(tmp_path / "missing")]) == 1
