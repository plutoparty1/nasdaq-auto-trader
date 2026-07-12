from __future__ import annotations

import sys
import time
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nasdaq_auto_trader.app_controller import AutoTradeController
from nasdaq_auto_trader.app_ui import DashboardApp
from nasdaq_auto_trader.config import AppConfig
from nasdaq_auto_trader.config_manager import TradingSettings
from nasdaq_auto_trader.dry_run_market_data import DryRunMarketData
from nasdaq_auto_trader.models import AccountSnapshot
from nasdaq_auto_trader.quant_data.symbol_selector import RankedSymbol, SelectionReport
from nasdaq_auto_trader.settings_window_dialog import SettingsWindow
from nasdaq_auto_trader.trading_session_store import TradingSessionStore


class CaptureError(RuntimeError):
    pass


def main(output_dir: str) -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.geometry("1x1+0+0")
    root.update()
    settings = TradingSettings(auto_symbol_selection_enabled=False)
    editor = SettingsWindow(root, settings, target / "trading.json")
    editor.window.geometry("980x760")
    editor.window.attributes("-topmost", True)
    _settle(editor.window)
    _capture(editor.window, target / "settings-manual.png")
    editor.variables["auto_symbol_selection_enabled"].set(True)
    _settle(editor.window)
    _capture(editor.window, target / "settings-automatic.png")
    states = (
        str(editor.widgets["ticker"].cget("state")),
        str(editor.widgets["ai_candidate_tickers"].cget("state")),
        str(editor.widgets["order_qty"].cget("state")),
    )
    canvas = _find_canvas(editor.window, tk.Canvas)
    canvas.yview_moveto(0.68)
    _settle(editor.window)
    _capture(editor.window, target / "settings-automatic-ai.png", top_offset=40)
    editor.window.destroy()
    root.destroy()

    dashboard_root = tk.Tk()
    dashboard_settings = TradingSettings(
        auto_symbol_selection_enabled=True,
        save_log=False,
    )
    controller = AutoTradeController(
        AppConfig(),
        engine_factory=_Factory(),
        trading_settings=dashboard_settings,
        settings_path=target / "trading.json",
        session_store=TradingSessionStore(target / "session.json"),
    )
    app = DashboardApp(
        dashboard_root,
        controller,
        tk_module=tk,
        ttk_module=ttk,
        messagebox_module=messagebox,
        config_path="config.example.json",
        portfolio_refresh_seconds=60,
    )
    dashboard_root.attributes("-topmost", True)
    _settle(dashboard_root)
    app.learning_button.invoke()
    _pump(dashboard_root, 2.0)
    learning_log = app.log_text.get("1.0", "end")
    if "제출된 실제 주문: 0건" not in learning_log:
        raise CaptureError("learning-only flow did not prove zero submitted orders")
    _capture(dashboard_root, target / "dashboard-learning.png")
    app.start_button.invoke()
    _pump(dashboard_root, 2.0)
    _settle(dashboard_root)
    _capture(dashboard_root, target / "dashboard-selected.png")
    dashboard_root.destroy()
    print(f"ticker={states[0]} candidates={states[1]} order_qty={states[2]}")
    return 0


class _Factory:
    def __call__(self, config, **kwargs):
        del config, kwargs
        return _Engine()


class _Engine:
    market_data = DryRunMarketData()
    last_selection_report = SelectionReport(
        status="selected",
        universe_id="nasdaq_100",
        universe_effective_date="2026-07-10",
        strategy_id="learned-momentum",
        strategy_version="v1",
        strategy_digest="diagnostic",
        shortlist_count=30,
        ranked=(RankedSymbol("QQQ", 1.5, 0.82, ("momentum", "liquidity")),),
        selected_symbols=("QQQ",),
    )

    def run_once(self):
        return []

    def load_portfolio(self, refresh=False):
        del refresh
        return AccountSnapshot(10_000, 10_000, 10_000), {}


def _settle(window) -> None:
    window.deiconify()
    window.lift()
    window.focus_force()
    _pump(window, 1.0)


def _pump(window, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        window.update()
        time.sleep(0.02)


def _capture(window, path: Path, top_offset: int = 0) -> None:
    window.update_idletasks()
    x = window.winfo_rootx()
    y = window.winfo_rooty()
    width = window.winfo_width()
    height = window.winfo_height()
    for _attempt in range(5):
        image = ImageGrab.grab(
            bbox=(x, y + top_offset, x + width, y + height),
            all_screens=True,
        ).convert("RGB")
        if _black_pixel_ratio(image) < 0.05:
            image.save(path)
            return
        _pump(window, 0.5)
    raise CaptureError(f"window capture remained incomplete: {path.name}")


def _black_pixel_ratio(image) -> float:
    histogram = image.convert("L").histogram()
    black = sum(histogram[:5])
    return black / (image.width * image.height)


def _find_canvas(widget, canvas_type):
    for child in widget.winfo_children():
        if isinstance(child, canvas_type):
            return child
        found = _find_canvas_or_none(child, canvas_type)
        if found is not None:
            return found
    raise CaptureError("settings canvas not found")


def _find_canvas_or_none(widget, canvas_type):
    for child in widget.winfo_children():
        if isinstance(child, canvas_type):
            return child
        found = _find_canvas_or_none(child, canvas_type)
        if found is not None:
            return found
    return None


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
