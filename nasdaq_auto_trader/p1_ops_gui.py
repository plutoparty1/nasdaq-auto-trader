from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from tkinter import messagebox, ttk
from typing import final

from .app_ui_layout import DashboardLayoutMixin
from .gui_theme import apply_operator_theme
from .p1_ops_gui_contract import MODE_TEXT, OpsController, OpsStatus, WorkerResult
from .p1_ops_gui_review import LiveRequest, LiveReviewDialog


@final
class P1OpsApp(DashboardLayoutMixin):
    def __init__(self, root: tk.Tk, controller: OpsController) -> None:
        self.root, self.controller = root, controller
        self.tk, self.ttk = tk, ttk
        self.closed = False
        self.closing = False
        self.busy = False
        self.snapshot: OpsStatus = {}
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="p1-ops-gui")
        self._results: queue.Queue[tuple[str, Future[WorkerResult]]] = queue.Queue()
        self._review_dialog: LiveReviewDialog | None = None
        root.title("NASDAQ Auto Trader · P1 운영")
        root.geometry("1160x720")
        root.minsize(940, 620)
        apply_operator_theme(root, ttk)
        self._build_ui()
        self._adapt_layout()
        root.protocol("WM_DELETE_WINDOW", self._request_close)
        _ = self._submit("status", lambda: WorkerResult(status=self.controller.status()))
        self._poll_id = root.after(50, self._poll_results)
        self._tick_id = root.after(15000, self._tick)

    def _adapt_layout(self) -> None:
        self.start_button.configure(text="선택 모드 시작")
        self.pause_button.configure(text="신규 진입 일시정지")
        self.resume_button.configure(text="신규 진입 재개")
        self.refresh_button.configure(text="지금 점검 / 새로고침")
        self.learning_button.configure(text="실전 검토 / 요청")
        self.cancel_learning_button.configure(text="프로그램 종료")
        self.report_button.grid_remove()
        for index, button in enumerate((self.start_button, self.pause_button, self.resume_button,
                                        self.refresh_button, self.learning_button, self.cancel_learning_button)):
            button.grid(row=index // 3, column=index % 3)
        self.log_text.configure(width=42)
        footer = self.root.grid_slaves(row=5)[0]
        self.selected_mode = tk.StringVar(self.root, value="local_paper")
        self.mode_combo = ttk.Combobox(
            footer, textvariable=self.selected_mode, values=tuple(MODE_TEXT), state="readonly", width=16,
        )
        self.mode_combo.grid(row=1, column=0, sticky="w", pady=(8, 0))
        _ = self.mode_combo.bind("<<ComboboxSelected>>", self._mode_selected)
        self.positions_tree.heading("latest_price", text="최고가")
        self.warning_label.configure(justify="left", wraplength=1100)
        _ = self.root.bind("<Configure>", self._resize)
        self._mode_selected()

    def _resize(self, event: tk.Event) -> None:
        if event.widget == self.root:
            self.warning_label.configure(wraplength=max(400, event.width - 32))
            for row in (2, 5):
                for widget in self.root.grid_slaves(row=row):
                    labels = [widget] if row == 2 else widget.winfo_children()
                    for label in labels:
                        if isinstance(label, ttk.Label):
                            _ = label.configure(wraplength=max(400, event.width - 32))

    def _mode_selected(self, _event: tk.Event | None = None) -> None:
        selected = self.selected_mode.get()
        shown = self.snapshot.get("mode", "local_paper")
        mode_text = MODE_TEXT[selected]
        if selected != shown:
            mode_text += f" · 현재 표시: {MODE_TEXT[shown].split('·')[0].strip()}"
        self.mode_var.set(mode_text)
        self.warning_var.set(
            "실전 주문 차단 · 운영·수익성 미검증. 신규 진입을 멈춰도 보유 보호·주문 대사는 계속됩니다. "
            "프로그램을 종료하면 보호 점검도 종료됩니다."
        )

    def _submit(self, kind: str, action: Callable[[], WorkerResult]) -> bool:
        if self.busy or self.closing:
            return False
        self.busy = True
        self._update_controls()
        future = self._worker.submit(action)
        future.add_done_callback(lambda completed: self._results.put((kind, completed)))
        return True

    def _action(self, callback: Callable[[], None]) -> WorkerResult:
        failure = ""
        try:
            callback()
        except Exception as error:  # noqa: BLE001 - GUI boundary redacts broker errors before display.
            failure = type(error).__name__
        return WorkerResult(status=self.controller.status(), error=failure)

    def _start_auto_trading(self) -> None:
        mode = self.selected_mode.get()
        _ = self._submit("status", lambda: self._action(lambda: self.controller.start(mode)))

    def _pause_auto_trading(self) -> None:
        _ = self._submit("status", lambda: self._action(self.controller.pause_entries))

    def _resume_auto_trading(self) -> None:
        _ = self._submit("status", lambda: self._action(self.controller.resume_entries))

    def _refresh_now(self) -> None:
        _ = self._submit("status", lambda: self._action(self.controller.step))

    def _start_learning_only(self) -> None:
        _ = self._submit("review", lambda: WorkerResult(review=self.controller.live_review()))

    def _cancel_learning(self) -> None:
        self._request_close()

    def _open_latest_report(self) -> None:
        self._start_learning_only()

    def _save_request(self, request: LiveRequest) -> bool:
        return self._submit("status", lambda: self._action(lambda: self.controller.record_live_request(
            request.account, request.allocation_usd, request.loss_stop_pct, request.confirm,
        )))

    def _poll_results(self) -> None:
        while not self._results.empty():
            kind, future = self._results.get_nowait()
            try:
                result = future.result()
            except Exception as error:  # noqa: BLE001 - Tk boundary must never echo account-bearing errors.
                self.status_var.set("오류 · 요청 미완료")
                self._append_log(f"요청 실패 ({type(error).__name__}). 실행 상태와 차단 사유를 확인하세요.")
                if kind == "close":
                    self.closing = False
                result = None
            if kind == "close" and self.closing:
                self._worker.shutdown(wait=True)
                self.closed = True
                self.root.destroy()
                return
            if result is not None:
                if result.review is not None:
                    if self._review_dialog and self._review_dialog.window.winfo_exists():
                        self._review_dialog.window.destroy()
                    self._review_dialog = LiveReviewDialog(self.root, result.review, self._save_request)
                if result.status is not None:
                    self._render_status(result.status)
                if result.error:
                    self.status_var.set("오류 · 요청 미완료")
                    self._append_log(f"요청 실패 ({result.error}). 위 상태와 차단 사유를 확인하세요.")
            if not self.closing:
                self.busy = False
            self._update_controls()
        self._poll_id = self.root.after(50, self._poll_results)

    def _render_status(self, status: OpsStatus) -> None:
        self.snapshot = status
        running = status.get("running", False)
        paused = status.get("entries_paused", False)
        self.status_var.set("신규 진입 정지 · 보호 점검 중" if running and paused else "운영 중" if running else "정지")
        if running:
            self.selected_mode.set(status.get("mode", "local_paper"))
        self._mode_selected()
        self.cash_var.set(f"현금 ${status.get('cash', 0):,.2f}")
        self.equity_var.set(f"평가 ${status.get('equity', 0):,.2f}")
        pending = status.get("pending", [])
        self.buying_power_var.set(f"미결 주문 {len(pending) if isinstance(pending, list) else pending}건")
        self.updated_var.set(f"갱신 {status.get('updated_at', '-')}")
        self.selection_var.set(f"P1 고정 전략 · {status.get('version', '미확인')} · {status.get('message', '대기')}")
        children = self.positions_tree.get_children()
        if children:
            self.positions_tree.delete(*children)
        for position in status.get("positions", []):
            qty, entry = position["qty"], position["avg_entry_price"]
            value = position["market_value"]
            pnl = value - qty * entry
            high_water = position.get("high_water_price")
            self.positions_tree.insert("", "end", values=(
                position["symbol"], f"{qty:g}", f"{entry:,.2f}",
                f"{high_water:,.2f}" if high_water is not None else "-",
                f"{value:,.2f}",
                f"{pnl:+,.2f}", f"{pnl / (qty * entry) * 100:+.2f}%" if qty * entry else "-",
            ))
        blockers = status.get("blockers", [])
        self._append_log("\n".join(filter(None, [status.get("message", "대기"),
            status.get("account_message", ""), *status.get("no_buy_reasons", []), *blockers])))

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        if int(self.log_text.index("end-1c").split(".")[0]) > 2000:
            self.log_text.delete("1.0", "501.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _update_controls(self) -> None:
        running, paused = self.snapshot.get("running", False), self.snapshot.get("entries_paused", False)
        enabled = not self.busy and not self.closing
        for button, allowed in (
            (self.start_button, enabled and not running), (self.pause_button, enabled and running and not paused),
            (self.resume_button, enabled and running and paused), (self.refresh_button, enabled),
            (self.learning_button, enabled), (self.cancel_learning_button, not self.closing),
        ):
            button.configure(state="normal" if allowed else "disabled")
        _ = self.mode_combo.configure(state="readonly" if enabled and not running else "disabled")

    def _tick(self) -> None:
        if self.closing:
            return
        if self.snapshot.get("running", False):
            self._refresh_now()
        self._tick_id = self.root.after(15000, self._tick)

    def _request_close(self) -> None:
        if messagebox.askokcancel(
            "P1 운영 종료", "종료하면 보유 보호·주문 대사도 중단됩니다.\n"
            "증권사 미결 주문은 취소되지 않고 남을 수 있습니다.\n프로그램을 종료할까요?", parent=self.root,
        ):
            self.close()

    def close(self) -> None:
        if self.closing or self.closed:
            return
        self.closing = True
        self.root.after_cancel(self._tick_id)
        self.status_var.set("종료 중 · 작업 완료 대기")
        self._update_controls()
        def close_worker() -> WorkerResult:
            self.controller.close()
            return WorkerResult()
        future = self._worker.submit(close_worker)
        future.add_done_callback(lambda completed: self._results.put(("close", completed)))


def launch_p1_ops_gui(controller: OpsController, *, auto_start_local: bool = False) -> None:
    root = tk.Tk()
    app = P1OpsApp(root, controller)
    if auto_start_local:
        def start_when_ready() -> None:
            if app.busy:
                _ = root.after(50, start_when_ready)
            elif not app.closing and app.selected_mode.get() == "local_paper":
                app._start_auto_trading()
        _ = root.after(50, start_when_ready)
    root.mainloop()
