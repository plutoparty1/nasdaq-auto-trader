from __future__ import annotations

import queue
import threading
from dataclasses import replace
from pathlib import Path

from .ai_quant_lab.artifact_paths import default_strategy_artifact_paths
from .app_controller import AutoTradeController
from .app_types import GuiUnavailableError
from .config import AppConfig
from .config_manager import (
    SettingsError,
    TradingSettings,
    default_settings_path,
    load_or_create_settings,
)
from .app_ui_actions import DashboardActionsMixin
from .app_ui_layout import DashboardLayoutMixin
from .app_ui_render import DashboardRenderMixin
from .gui_theme import apply_operator_theme
from .daily_report import DailyReportService
from .quant_data.resources import application_data_root
from .runtime_journal import RuntimeJournal


def launch_gui(
    config: AppConfig,
    config_path: str | Path | None = None,
    trade_interval_seconds: float = 60 * 60,
    portfolio_refresh_seconds: float = 15,
    settings_path: str | Path | None = None,
    start_paused: bool = False,
) -> None:
    """Launch the Tkinter management GUI."""

    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except ImportError as exc:  # pragma: no cover - platform dependent
        raise GuiUnavailableError("Tkinter is required to run the desktop GUI") from exc

    settings_file = Path(settings_path) if settings_path else default_settings_path()
    settings_error = None
    try:
        trading_settings = load_or_create_settings(settings_file)
    except SettingsError as exc:
        trading_settings = TradingSettings()
        settings_error = str(exc)
    trading_settings = replace(
        trading_settings,
        auto_symbol_selection_enabled=True,
        unattended_operation_enabled=True,
        unattended_live_trading_enabled=(
            trading_settings.live_trading and not trading_settings.dry_run
        ),
        require_confirm_before_buy=False,
        require_confirm_before_sell=False,
    )

    runtime_journal = RuntimeJournal(
        default_strategy_artifact_paths().audit_log_path
    )
    controller = AutoTradeController(
        config,
        interval_seconds=trade_interval_seconds,
        trading_settings=trading_settings,
        settings_path=settings_file,
        settings_error=settings_error,
        runtime_journal=runtime_journal,
    )
    root = tk.Tk()
    DashboardApp(
        root,
        controller,
        tk_module=tk,
        ttk_module=ttk,
        messagebox_module=messagebox,
        config_path=config_path,
        portfolio_refresh_seconds=portfolio_refresh_seconds,
        start_paused=start_paused,
    )
    root.mainloop()


class DashboardApp(
    DashboardLayoutMixin,
    DashboardActionsMixin,
    DashboardRenderMixin,
):
    def __init__(
        self,
        root,
        controller: AutoTradeController,
        tk_module,
        ttk_module,
        messagebox_module,
        config_path: str | Path | None,
        portfolio_refresh_seconds: float,
        start_paused: bool = False,
    ) -> None:
        self.root = root
        self.controller = controller
        self.tk = tk_module
        self.ttk = ttk_module
        self.messagebox = messagebox_module
        self.config_path = str(config_path) if config_path else "(default config)"
        self.portfolio_refresh_seconds = max(float(portfolio_refresh_seconds), 1.0)
        self._result_queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._next_portfolio_refresh = 0.0
        self._take_profit_symbols: set[str] = set()
        self._daily_report_service = DailyReportService(
            application_data_root() / "reports",
            default_strategy_artifact_paths().audit_log_path,
            controller.runtime_journal,
        )

        self.root.title("NASDAQ Auto Trader")
        self.root.geometry("1080x700")
        self.root.minsize(940, 580)
        apply_operator_theme(self.root, self.ttk)
        self._build_ui()
        self._append_log("프로그램 시작")
        self._append_log("AI 완전자동 운영 모드")
        self._append_log(f"브로커 구성 파일: {self.config_path}")
        if self.controller.settings_error:
            self._append_log(f"설정 오류: {self.controller.settings_error}")
            self.messagebox.showerror(
                "설정 오류",
                "trading_config.json을 불러오지 못했습니다. 자동매매 시작이 차단됩니다.\n\n"
                + self.controller.settings_error,
            )
        self._render_mode()
        if start_paused:
            self._append_log("자동매매 시작 대기: '자동매매 실행'을 눌러 시작하세요.")
        if start_paused or not self._start_unattended_operation():
            self._start_task("portfolio", self.controller.refresh_portfolio)
        self._poll_results()
        self._tick()
