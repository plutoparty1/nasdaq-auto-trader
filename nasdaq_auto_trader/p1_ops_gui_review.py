from __future__ import annotations

import json
import math
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import final

from .gui_theme import PAPER
from .p1_ops_gui_contract import CONFIRMATION, LiveReview


@dataclass(frozen=True, slots=True)
class LiveRequest:
    account: str
    allocation_usd: float
    loss_stop_pct: float
    confirm: str


@final
class LiveReviewDialog:
    def __init__(
        self, root: tk.Tk, review: LiveReview, submit: Callable[[LiveRequest], bool],
    ) -> None:
        self.submit = submit
        self.window = tk.Toplevel(root)
        self.window.title("P1 실전 검토 · LIVE BLOCKED")
        self.window.geometry("900x820")
        self.window.minsize(760, 720)
        self.window.transient(root)
        _ = self.window.columnconfigure(0, weight=1)
        _ = self.window.rowconfigure(1, weight=1)
        ttk.Label(
            self.window, text="실전 차단 유지 · 아래 요청을 저장해도 주문할 수 없습니다",
            style="Selection.TLabel", wraplength=840,
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        table_area = ttk.Frame(self.window)
        table_area.grid(row=1, column=0, sticky="nsew", padx=12)
        _ = table_area.columnconfigure(0, weight=1)
        _ = table_area.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(table_area, background=PAPER, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table_area, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        _ = self.canvas.configure(yscrollcommand=scrollbar.set)
        table = ttk.Frame(self.canvas, padding=12)
        self.table_item = self.canvas.create_window(0, 0, window=table, anchor="nw")
        _ = table.columnconfigure(1, weight=1)
        rows = (
            ("계좌", "account", "미지정 · 전체 계좌번호는 표시하지 않음"),
            ("전략 / 버전", "version", "P1 / 버전 미확인"),
            ("실행 경로", "execution", "P1 Python 소스 실행"),
            ("종목 범위", "universe", "검토 자료 없음"),
            ("진입 / 청산", "conditions", "검토 자료 없음"),
            ("비중 / 한도", "caps", "검토 자료 없음"),
            ("요청 배정 (USD)", "allocation_usd", "미승인"),
            ("요청 손실 중단", "loss_stop_pct", "미승인"),
            ("기존 보유 인수", "existing_holdings", "NO · 기존 보유 종목 인수 안 함"),
            ("수수료 / 슬리피지", "fees", "실제 비용 미검증"),
            ("운영 / 수익성", "readiness", "실전 운영·수익성 미검증"),
            ("승인 상태", "approval", "요청 저장은 승인이 아님"),
            ("차단 사유", "blockers", "실전 게이트 승인 없음"),
            ("필요한 조치", "required_action", "실전 승인 요건을 확인하세요."),
        )
        self.value_labels: list[ttk.Label] = []
        for index, (title, key, fallback) in enumerate(rows):
            ttk.Label(table, text=title).grid(row=index, column=0, sticky="nw", pady=4, padx=(0, 16))
            value = review.get(key, fallback)
            rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            if key == "loss_stop_pct" and isinstance(value, (int, float)):
                rendered = f"{value * 100:g}%"
            label = ttk.Label(table, text=rendered, wraplength=640, justify="left")
            label.grid(row=index, column=1, sticky="nw", pady=4)
            self.value_labels.append(label)
        form = ttk.LabelFrame(self.window, text="명시적 실전 요청 기록", padding=12)
        form.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        _ = form.columnconfigure(1, weight=1)
        self.account = tk.StringVar(root)
        self.allocation = tk.StringVar(root)
        self.loss_stop = tk.StringVar(root)
        self.confirm = tk.StringVar(root)
        fields = (
            ("실전 계좌", self.account), ("배정 금액 (USD)", self.allocation),
            ("손실 중단 (%)", self.loss_stop), ("확인 문구", self.confirm),
        )
        for index, (title, variable) in enumerate(fields):
            ttk.Label(form, text=title).grid(row=index, column=0, sticky="w", pady=4, padx=(0, 12))
            entry = ttk.Entry(form, textvariable=variable, show="*" if index == 0 else "")
            entry.grid(row=index, column=1, sticky="ew", pady=4)
        self.phrase = str(review.get("confirmation_phrase", CONFIRMATION))
        ttk.Label(form, text=f"확인 문구를 그대로 입력: {self.phrase}", wraplength=800).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=4,
        )
        self.feedback = tk.StringVar(root)
        ttk.Label(form, textvariable=self.feedback, wraplength=800).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=4,
        )
        buttons = ttk.Frame(form)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(8, 0))
        self.save_button = ttk.Button(buttons, text="요청만 저장 · 차단 유지", command=self.save)
        self.save_button.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="닫기", command=self.window.destroy).grid(row=0, column=1)
        _ = table.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        _ = self.canvas.bind("<Configure>", self._resize)

    def _resize(self, event: tk.Event) -> None:
        _ = self.canvas.itemconfigure(self.table_item, width=event.width)
        for label in self.value_labels:
            _ = label.configure(wraplength=max(320, event.width - 180))

    def save(self) -> None:
        try:
            allocation = float(self.allocation.get())
            loss_stop = float(self.loss_stop.get())
        except ValueError:
            self.feedback.set("배정 금액과 손실 중단에 숫자를 입력하세요.")
            return
        valid = (
            bool(self.account.get().strip()) and math.isfinite(allocation) and allocation > 0
            and math.isfinite(loss_stop) and 0 < loss_stop <= 20
            and self.confirm.get() == self.phrase
        )
        if not valid:
            self.feedback.set("계좌, 양수 금액, 0 초과~20% 손실 중단, 정확한 확인 문구가 필요합니다.")
            return
        request = LiveRequest(self.account.get().strip(), allocation, loss_stop / 100, self.confirm.get())
        if self.submit(request):
            self.account.set("")
            self.confirm.set("")
            self.feedback.set("요청 처리 중 · 결과는 운영 화면에서 확인하세요. 실전 차단은 유지됩니다.")
