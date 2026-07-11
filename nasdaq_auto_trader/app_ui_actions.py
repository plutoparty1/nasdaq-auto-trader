from __future__ import annotations

import queue
import threading
import time
import traceback
from typing import Any, Callable

from .app_types import AppConfigurationError
from .config_manager import SettingsError, TradingSettings
from .learning_runner import run_learning_only
from .settings_window import open_settings_window


class DashboardActionsMixin:
    def _start_auto_trading(self) -> None:
        try:
            interval_minutes = float(self.interval_var.get())
            if interval_minutes <= 0:
                raise AppConfigurationError("interval must be greater than zero")
            self.controller.start(interval_seconds=interval_minutes * 60)
        except (AppConfigurationError, SettingsError, ValueError) as exc:
            self.messagebox.showerror("자동매매 시작 실패", str(exc))
            self._append_log(f"자동매매 시작 실패: {exc}")
            return

        self._append_log("자동매매 실행")
        self._start_task("auto", lambda: self.controller.run_auto_cycle(force=True))
        self._update_controls()

    def _pause_auto_trading(self) -> None:
        self.controller.pause()
        self._append_log("자동매매 정지: 진행 중인 API 요청은 완료 후 멈춥니다.")
        self._update_controls()

    def _resume_auto_trading(self) -> None:
        try:
            self.controller.resume()
        except SettingsError as exc:
            self.messagebox.showerror("자동매매 재개 실패", str(exc))
            self._append_log(f"자동매매 재개 실패: {exc}")
            return
        self._append_log("자동매매 재개")
        self._start_task("auto", lambda: self.controller.run_auto_cycle(force=True))
        self._update_controls()

    def _refresh_now(self) -> None:
        self._start_task("portfolio", self.controller.refresh_portfolio)

    def _start_learning_only(self) -> None:
        if self._start_task("learn", run_learning_only):
            self._append_log("학습만 실행: 실제 주문 없이 전략 연구와 검증만 실행합니다.")
            self._update_controls()

    def _open_settings(self) -> None:
        open_settings_window(
            self.root,
            self.controller.trading_settings,
            self.controller.settings_path,
            on_save=self._settings_saved,
        )

    def _settings_saved(self, settings: TradingSettings) -> None:
        self.controller.update_settings(settings)
        self._append_log("설정 저장 및 내부 설정 갱신 완료")
        self._render_mode()
        self._start_task("portfolio", self.controller.refresh_portfolio)

    def _tick(self) -> None:
        now = time.monotonic()
        if self._worker is None:
            if self.controller.is_due():
                self._start_task("auto", self.controller.run_auto_cycle)
            elif now >= self._next_portfolio_refresh:
                self._start_task("portfolio", self.controller.refresh_portfolio)
        self._update_controls()
        self.root.after(1000, self._tick)

    def _poll_results(self) -> None:
        while True:
            try:
                kind, label, payload = self._result_queue.get_nowait()
            except queue.Empty:
                break

            self._worker = None
            if kind == "ok" and label == "portfolio":
                self._render_snapshot(payload)
                self._next_portfolio_refresh = time.monotonic() + self.portfolio_refresh_seconds
            elif kind == "ok" and label == "auto":
                self._render_auto_results(payload)
                self._start_task("portfolio", self.controller.refresh_portfolio)
            elif kind == "ok" and label == "learn":
                self._render_learning_result(payload)
            elif kind == "error":
                message, details = payload
                self.status_var.set("오류")
                self._append_log(f"오류: {message}")
                self._append_log(details)
                self._next_portfolio_refresh = time.monotonic() + self.portfolio_refresh_seconds
        self.root.after(250, self._poll_results)

    def _start_task(self, label: str, task: Callable[[], Any]) -> bool:
        if self._worker is not None:
            return False

        def runner() -> None:
            try:
                self._result_queue.put(("ok", label, task()))
            except Exception as exc:  # noqa: BROAD_EXCEPT_OK
                self._result_queue.put(("error", label, (str(exc), traceback.format_exc())))

        self.status_var.set("요청 처리 중")
        self._worker = threading.Thread(target=runner, daemon=True)
        self._worker.start()
        return True
