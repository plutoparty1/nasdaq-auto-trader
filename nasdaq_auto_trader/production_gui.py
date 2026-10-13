from __future__ import annotations

import json
import queue
import tkinter as tk
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from tkinter import messagebox, ttk

from .ai_quant_lab.types import JsonObject
from .app_ui_layout import DashboardLayoutMixin
from .gui_theme import PAPER_RAISED, apply_operator_theme
from .production_fees import FeeScheduleInput
from .production_gui_actions import (
    ProductionFacade,
    approval_window_text,
    confirm_prepared_start,
    review_summary,
)


class ProductionApp(DashboardLayoutMixin):
    def __init__(self, root: tk.Tk, service: ProductionFacade) -> None:
        self.root, self.service = root, service
        self.controller = service.controller
        self.tk, self.ttk = tk, ttk
        self.busy = self.closing = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="production-gui")
        self._results: queue.Queue[tuple[str, Future[JsonObject]]] = queue.Queue()
        self._review_window: tk.Toplevel | None = None
        root.title("NASDAQ Auto Trader · 정식 운영")
        root.geometry("1160x720")
        root.minsize(940, 620)
        apply_operator_theme(root, ttk)
        self._build_ui()
        actions = (
            (self.start_button, "자동 사전점검 후 시작", self._start_auto_trading),
            (self.pause_button, "신규 진입 중지", self._pause_auto_trading),
            (self.cancel_learning_button, "전체 종료", self._cancel_learning),
        )
        self._buttons: list[ttk.Button] = []
        for index, (button, label, command) in enumerate(actions):
            button.configure(text=label, command=command)
            button.grid(row=index // 2, column=index % 2)
            self._buttons.append(button)
        for button in (self.report_button, self.refresh_button, self.learning_button, self.resume_button):
            button.grid_remove()
        self.warning_label.configure(wraplength=900, justify="left")
        self.warning_var.set("시작 대기 · 승인 전 실주문 차단. 신규 진입 중지는 승인 유효 기간 안에서만 보호 매도를 유지합니다. "
                             "전체 종료는 보호·대사도 멈춥니다. 취소·청산은 자동 수행하지 않습니다.")
        root.protocol("WM_DELETE_WINDOW", self._request_close)
        self._render(service.status())
        self._poll_id = root.after(100, self._poll_results)
        self._tick_id = root.after(1000, self._tick)

    def _submit(self, kind: str, action: Callable[[], JsonObject]) -> None:
        if self.busy or self.closing:
            return
        self.busy = True
        self._controls()
        future = self._executor.submit(action)
        future.add_done_callback(lambda completed: self._results.put((kind, completed)))

    def _start_auto_trading(self) -> None:
        self._submit("review", self.service.prepare_start)

    def _refresh_now(self) -> None:
        self._start_auto_trading()

    def _start_learning_only(self) -> None:
        self._start_auto_trading()

    def _resume_auto_trading(self) -> None:
        self._start_auto_trading()

    def _pause_auto_trading(self) -> None:
        self._submit("status", self.service.stop_entries)

    def _cancel_learning(self) -> None:
        self._request_close()

    def _open_latest_report(self) -> None:
        self._start_learning_only()

    def _tick(self) -> None:
        if not self.closing and self.controller.is_due():
            def cycle() -> JsonObject:
                results = self.controller.run_operating_cycle()
                status = self.service.status()
                status["cycle_result_count"] = len(results) if results is not None else 0
                return status
            self._submit("status", cycle)
        if not self.closing:
            self._tick_id = self.root.after(1000, self._tick)

    def _poll_results(self) -> None:
        while not self._results.empty():
            kind, future = self._results.get_nowait()
            result: JsonObject
            try:
                result = future.result()
            except Exception as error:  # noqa: BLE001
                result = {"status": "error", "error_type": type(error).__name__}
            if kind == "close":
                self._executor.shutdown(wait=True)
                self.root.destroy()
                return
            self.busy = False
            self._render(result)
            if kind == "review":
                self._show_review(result)
            self._controls()
        self._poll_id = self.root.after(100, self._poll_results)

    def _render(self, result: JsonObject) -> None:
        self.status_var.set(str(result.get("status", "시작 대기")))
        self.mode_var.set(f"모드: {result.get('mode', '대기')} · 승인 상태: {result.get('approval_status', '미승인')}")
        self.selection_var.set(f"기존 수정 전략 · {result.get('strategy_id', 'builtin_ai_volatility_target')}")
        self._append_log(json.dumps(result, ensure_ascii=False, indent=2))

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _controls(self) -> None:
        for button in self._buttons:
            button.configure(state="disabled" if self.busy or self.closing else "normal")

    def _show_review(self, review: JsonObject) -> None:
        if self._review_window is not None and self._review_window.winfo_exists():
            self._review_window.destroy()
        window = tk.Toplevel(self.root)
        self._review_window = window
        window.title("최종 조건 검토 · 미승인 초안")
        window.geometry("760x700")
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text="계좌·전략·실행본·최종 설정과 차단 사유를 확인하세요.").grid(row=0, sticky="w")
        text = tk.Text(frame, wrap="word", background=PAPER_RAISED)
        text.grid(row=1, sticky="nsew", pady=8)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=8)
        text.configure(yscrollcommand=scrollbar.set)
        text.insert("1.0", review_summary(review))
        text.configure(state="disabled")
        ttk.Label(frame, text=approval_window_text(review),
                  wraplength=700).grid(row=2, sticky="w", pady=8)
        phrase = review.get("confirmation_phrase", "미확인")
        ttk.Label(frame, text=f"승인 문구: {phrase}", wraplength=700).grid(row=3, sticky="w")
        confirmation = tk.StringVar(window)
        ttk.Entry(frame, textvariable=confirmation).grid(row=4, sticky="ew", pady=8)
        def authorize() -> None:
            entered = confirmation.get()
            self._submit("status", lambda: confirm_prepared_start(self.service, confirmation=entered, review=review))
            window.destroy()
        blocked = bool(review.get("blockers")) or review.get("status") != "ready_for_explicit_approval"
        ttk.Button(frame, text="실거래 시작 확인", command=authorize,
                   state="disabled" if blocked else "normal").grid(row=5, sticky="w")
        if blocked:
            ttk.Label(frame, text="차단 사유 해소 전에는 승인·운영을 시작할 수 없습니다.", wraplength=700).grid(row=6, sticky="w")
        ttk.Button(frame, text="증권사 자료로 실제 수수료 입력", command=self._show_fee_input).grid(row=7, sticky="w", pady=8)

    def _show_fee_input(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("실제 수수료 자료 입력 · 추정값 금지")
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="KIS HTS/MTS 거래내역의 수수료·제비용, 적용 우대요율, 최소 수수료,\n"
                  "USD 기준과 적용 기간을 확인하세요. 확인되지 않은 값은 입력하지 마세요.",
                  wraplength=700).grid(row=0, columnspan=2, sticky="w")
        fields: list[tk.StringVar] = []
        for index, label in enumerate(("편도 수수료율 (%)", "최소 수수료 (USD)", "매도 세금·제비용률 (%)",
                                       "확인 자료·계좌 우대·통화·적용 기간"), 1):
            ttk.Label(frame, text=label).grid(row=index, column=0, sticky="w", pady=8)
            value = tk.StringVar(window)
            fields.append(value)
            ttk.Entry(frame, textvariable=value, width=52).grid(row=index, column=1, sticky="ew", pady=8)
        def save() -> None:
            try:
                profile = FeeScheduleInput(float(fields[0].get()) / 100, float(fields[1].get()),
                                           float(fields[2].get()) / 100, fields[3].get())
            except ValueError:
                messagebox.showerror("입력 오류", "증권사 자료의 숫자를 입력하세요. 추정값으로 저장하지 마세요.", parent=window)
                return
            if not messagebox.askokcancel("실제 자료 확인", "입력값은 실제 계좌에 적용되는 증권사 자료로 확인했습니까?\n"
                                          "저장은 실전 승인이 아니며 사전점검이 다시 필요합니다.", parent=window):
                return
            self._submit("status", lambda: self.service.configure_fee_profile(profile))
            window.destroy()
            if self._review_window is not None and self._review_window.winfo_exists():
                self._review_window.destroy()
        ttk.Button(frame, text="확인한 실제 자료만 저장 · 다시 사전점검", command=save).grid(row=5, columnspan=2, sticky="w", pady=8)

    def _request_close(self) -> None:
        if self.closing:
            return
        if not messagebox.askokcancel("전체 종료", "보호 매도와 주문 대사도 중단됩니다.\n"
                                     "미체결 취소·보유 청산 없이 종료할까요?", parent=self.root):
            return
        self.closing = True
        self.root.after_cancel(self._tick_id)
        self._controls()
        future = self._executor.submit(self.service.shutdown)
        future.add_done_callback(lambda completed: self._results.put(("close", completed)))


def launch_production_gui(service: ProductionFacade) -> None:
    root = tk.Tk()
    ProductionApp(root, service)
    root.mainloop()
