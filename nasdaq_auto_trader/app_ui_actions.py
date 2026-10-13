from __future__ import annotations

import queue
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from typing import Any, Callable

from .app_types import AppConfigurationError
from .config_manager import SettingsError


class DashboardActionsMixin:
    def _start_unattended_operation(self) -> bool:
        settings = self.controller.trading_settings
        if settings.unattended_operation_enabled is not True:
            return False
        try:
            self.controller.start(
                interval_seconds=settings.unattended_interval_minutes * 60
            )
        except (AppConfigurationError, SettingsError) as exc:
            self._append_log(f"무인 자동운영 시작 실패: {exc}")
            return False
        self._append_log(
            f"무인 자동운영 시작: {settings.unattended_interval_minutes}분 간격"
        )
        started = self._start_task(
            "auto",
            lambda: self.controller.run_operating_cycle(force=True),
        )
        if started:
            self.controller.record_unattended_start()
        self._update_controls()
        return started

    def _start_auto_trading(self) -> None:
        try:
            self.controller.start(
                interval_seconds=self.controller.trading_settings.unattended_interval_minutes * 60
            )
        except (AppConfigurationError, SettingsError) as exc:
            self.messagebox.showerror("자동매매 시작 실패", str(exc))
            self._append_log(f"자동매매 시작 실패: {exc}")
            return

        self._append_log(f"자동매매 실행: {self.controller.interval_seconds / 60:g}분 간격")
        self._start_task("auto", lambda: self.controller.run_operating_cycle(force=True))
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
        self._start_task("auto", lambda: self.controller.run_operating_cycle(force=True))
        self._update_controls()

    def _refresh_now(self) -> None:
        self._start_task("portfolio", self.controller.refresh_portfolio)

    def _start_learning_only(self) -> None:
        if self._start_task("learn", self.controller.run_learning_only):
            self._append_log("학습만 실행: 실제 주문 없이 전략 연구와 검증만 실행합니다.")
            self._update_controls()

    def _cancel_learning(self) -> None:
        self.controller.cancel_learning()
        self._append_log("학습 취소 요청을 보냈습니다.")

    def _open_latest_report(self) -> None:
        path = self._daily_report_service.latest_path()
        if path is None:
            self.messagebox.showinfo("전일 보고서", "아직 생성된 전일 보고서가 없습니다.")
            return
        if not webbrowser.open(path.resolve().as_uri()):
            self.messagebox.showerror(
                "전일 보고서",
                f"보고서를 열지 못했습니다.\n{path}",
            )

    def _tick(self) -> None:
        now = time.monotonic()
        if self._worker is None:
            wall_clock = datetime.now().astimezone()
            if self.controller.is_due():
                self._start_task("auto", self.controller.run_operating_cycle)
            elif self._daily_report_service.is_due(
                wall_clock,
                self.controller.trading_settings,
            ):
                self._start_task(
                    "report",
                    lambda: self._daily_report_service.generate(
                        wall_clock,
                        self.controller.trading_settings,
                        self.controller.last_snapshot,
                    ),
                )
            elif now >= self._next_portfolio_refresh:
                self._start_task("portfolio", self.controller.refresh_portfolio)
        self._update_controls()
        self.root.after(1000, self._tick)

    def _poll_results(self) -> None:
        handled_result = False
        pending_take_profit_symbols: set[str] = set()
        while True:
            try:
                kind, label, payload = self._result_queue.get_nowait()
            except queue.Empty:
                break

            handled_result = True
            self._worker = None
            if kind == "ok" and label == "portfolio":
                self._render_snapshot(payload)
                now = time.monotonic()
                self._next_portfolio_refresh = now + self.portfolio_refresh_seconds
                touched_symbols = {
                    position.symbol
                    for position in payload.positions
                    if position.unrealized_pl_pct is not None
                    and position.unrealized_pl_pct
                    >= self.controller.trading_settings.take_profit_rate
                }
                new_symbols = touched_symbols - self._take_profit_symbols
                self._take_profit_symbols = touched_symbols
                pending_take_profit_symbols.intersection_update(touched_symbols)
                if self.controller.state == "running":
                    pending_take_profit_symbols.update(new_symbols)
            elif kind == "ok" and label == "auto":
                self._render_auto_results(payload)
                if self.controller.state != "paused":
                    self._start_task("portfolio", self.controller.refresh_portfolio)
            elif kind == "ok" and label == "learn":
                self._render_learning_result(payload)
            elif kind == "ok" and label == "report":
                self._render_daily_report(payload)
            elif kind == "error":
                message, details = payload
                if label == "portfolio":
                    self.status_var.set("보유현황 조회 재시도 예약")
                    self._append_log(
                        "보유현황 조회 실패, "
                        f"{self.portfolio_refresh_seconds:g}초 후 자동 재시도: {message}"
                    )
                else:
                    self.status_var.set("오류")
                    self._append_log(f"오류: {message}")
                self._append_log(details)
                self._next_portfolio_refresh = time.monotonic() + self.portfolio_refresh_seconds
        if pending_take_profit_symbols:
            started = self._start_task(
                "auto",
                lambda: self.controller.run_operating_cycle(force=True),
            )
            if started:
                self._append_log("익절 기준 감지: 즉시 매도 조건 재평가")
            else:
                self._take_profit_symbols.difference_update(
                    pending_take_profit_symbols
                )
        if handled_result:
            self._update_controls()
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
