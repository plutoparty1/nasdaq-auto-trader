from pathlib import Path
from unittest.mock import Mock

import pytest
import tkinter as tk

from nasdaq_auto_trader.config_manager import TradingSettings, load_or_create_settings
from nasdaq_auto_trader.settings_window_dialog import SettingsWindow
from nasdaq_auto_trader.settings_window_fields import SETTINGS_SECTIONS


def _editor(settings: TradingSettings, settings_path: Path) -> SettingsWindow:
    root = tk.Tcl()
    window = SettingsWindow.__new__(SettingsWindow)
    window.tk = tk
    window.variables = {
        name: tk.BooleanVar(master=root) if kind == "bool" else tk.StringVar(master=root)
        for _, fields in SETTINGS_SECTIONS
        for name, _, kind, _ in fields
    }
    window.widgets = {"ticker": Mock(), "ai_candidate_tickers": Mock()}
    window.settings_path = settings_path
    window.window = Mock()
    window.messagebox = Mock()
    window.on_save = Mock()
    window._load_into_variables(settings)
    return window


@pytest.mark.parametrize("enabled", [True, False])
def test_editing_visible_setting_preserves_hidden_daily_minimum(
    tmp_path: Path, enabled: bool,
) -> None:
    path = tmp_path / "settings.json"
    window = _editor(
        TradingSettings(
            auto_symbol_selection_enabled=True,
            daily_minimum_buy_enabled=enabled,
            automatic_session_authorization_enabled=True,
        ),
        path,
    )
    assert "daily_minimum_buy_enabled" not in window.variables
    window.variables["take_profit_rate"].set("6")

    window._save()

    saved = load_or_create_settings(path)
    assert saved.daily_minimum_buy_enabled is enabled
    assert saved.automatic_session_authorization_enabled is True
    assert saved.take_profit_rate == 6


def test_explicit_reset_restores_hidden_setting_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    window = _editor(
        TradingSettings(
            auto_symbol_selection_enabled=True,
            daily_minimum_buy_enabled=True,
            automatic_session_authorization_enabled=True,
        ),
        path,
    )

    window._reset_defaults()
    window._save()

    saved = load_or_create_settings(path)
    assert saved.daily_minimum_buy_enabled is False
    assert saved.automatic_session_authorization_enabled is False


def test_reloading_settings_replaces_hidden_settings_baseline(tmp_path: Path) -> None:
    window = _editor(TradingSettings(), tmp_path / "settings.json")
    updated = TradingSettings(
        auto_symbol_selection_enabled=True, daily_minimum_buy_enabled=True,
    )

    window._load_into_variables(updated)

    assert window._read_settings().daily_minimum_buy_enabled is True
