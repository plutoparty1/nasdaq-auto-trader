from dataclasses import replace
from pathlib import Path
import json

import pytest

from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_settings import TradingSettings
from nasdaq_auto_trader import safe_runtime
from nasdaq_auto_trader.safe_launcher import parse_action, isolate_runtime, load_effective_runtime


def test_safe_policy_removes_gui_and_broker_live_authorization():
    config = safe_runtime.sanitize_config(replace(AppConfig(), mode="live", allow_live_trading=True, live_environment_authorized=True))
    settings = safe_runtime.sanitize_settings(replace(TradingSettings(), live_trading=True, dry_run=False, daily_minimum_buy_enabled=True, daily_forced_order_enabled=True))
    assert config.mode == "dry_run"
    assert not config.allow_live_trading and not config.live_environment_authorized
    assert not config.kis.app_key and not config.alpaca.api_key
    assert settings.dry_run and not settings.live_trading
    assert not settings.daily_minimum_buy_enabled and not settings.daily_forced_order_enabled


def test_safe_launcher_rejects_every_live_cli_route():
    for args in (["--allow-live"], ["gui"], ["--config", "live.json"], ["--runtime-check", "--live"]):
        with pytest.raises(SystemExit):
            parse_action(args)
    assert parse_action([]) == ("gui", None)
    assert parse_action(["--runtime-check"]) == ("check", None)


def test_runtime_isolation_never_uses_operating_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "operating"))
    runtime = isolate_runtime(tmp_path / "release")
    assert runtime == tmp_path / "release" / "simulation" / "NasdaqAutoTrader"
    assert not (tmp_path / "operating").exists()


def test_actual_saved_live_flags_are_overridden_and_sources_unchanged(tmp_path: Path):
    config_path = tmp_path / "config.safe.json"
    settings_path = tmp_path / "trading_config.json"
    config_path.write_text(json.dumps({"mode": "live", "allow_live_trading": True, "risk": {"risk_per_trade_pct": 0.02}}))
    settings_path.write_text(json.dumps({"live_trading": True, "dry_run": False, "auto_symbol_selection_enabled": True, "daily_minimum_buy_enabled": True, "daily_forced_order_enabled": True, "stop_loss_rate": 8.0}))
    before = settings_path.read_bytes()
    runtime = load_effective_runtime(tmp_path)
    assert runtime.requested_settings.live_trading
    assert runtime.requested_settings.daily_minimum_buy_enabled
    assert runtime.config.mode == "dry_run"
    assert runtime.settings.dry_run and not runtime.settings.live_trading
    assert not runtime.settings.daily_minimum_buy_enabled
    assert runtime.config.risk.risk_per_trade_pct == 0.02
    assert runtime.config.strategy.stop_loss_pct == 0.08
    assert settings_path.read_bytes() == before


def test_missing_release_settings_fail_without_creating_defaults(tmp_path: Path):
    with pytest.raises(RuntimeError, match="safe_release_config_missing"):
        load_effective_runtime(tmp_path)
    assert not list(tmp_path.iterdir())
