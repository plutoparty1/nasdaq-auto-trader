from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable

from nasdaq_auto_trader.ai_quant_lab.operator_gui_theme import (
    COLOR_BORDER,
    COLOR_BUTTON,
    COLOR_BUTTON_ACTIVE,
    COLOR_INK,
    COLOR_MUTED,
    COLOR_PANEL,
    COLOR_SAFE,
    COLOR_WARNING,
    FONT_SMALL,
    FONT_TITLE,
)

ACTION_BUTTON_LABELS = {
    "status": "상태 새로고침",
    "nightly": "연구 실행",
    "champion-lock": "잠금 실행",
    "paper-shadow": "리허설 실행",
    "rollback": "no-trade 롤백",
    "live-guard": "차단 상태 확인",
}


def panel(parent: tk.Misc, row: int, title: str) -> tk.LabelFrame:
    frame = tk.LabelFrame(
        parent,
        text=title,
        bg=COLOR_PANEL,
        fg=COLOR_INK,
        font=FONT_TITLE,
        padx=16,
        pady=12,
        highlightbackground=COLOR_BORDER,
        highlightthickness=1,
    )
    frame.grid(row=row, column=0, sticky="ew", padx=16, pady=12 if row == 1 else 0)
    return frame


def action_row(
    parent: tk.Misc,
    row: int,
    key: str,
    title: str,
    description: str,
    safety_note: str,
    command: Callable[[], None],
) -> None:
    item = tk.Frame(parent, bg=COLOR_PANEL)
    item.grid(row=row, column=0, sticky="ew", pady=(0, 9))
    item.columnconfigure(0, weight=1)
    tk.Label(item, text=title, bg=COLOR_PANEL, fg=COLOR_INK, font=FONT_TITLE).grid(
        row=0,
        column=0,
        sticky="w",
    )
    _wrapped_label(item, description, COLOR_MUTED).grid(row=1, column=0, sticky="w", pady=(2, 0))
    note_color = COLOR_WARNING if key in ("champion-lock", "nightly") else COLOR_SAFE
    _wrapped_label(item, safety_note, note_color).grid(row=2, column=0, sticky="w", pady=(2, 0))
    tk.Button(
        item,
        text=ACTION_BUTTON_LABELS[key],
        command=command,
        bg=COLOR_BUTTON,
        fg="#ffffff",
        activebackground=COLOR_BUTTON_ACTIVE,
        activeforeground="#ffffff",
        relief="flat",
        padx=12,
        pady=6,
        font=FONT_SMALL,
    ).grid(row=0, column=1, rowspan=3, sticky="e", padx=(12, 0))


def field(
    parent: tk.Misc,
    row: int,
    column: int,
    label: str,
    variable: tk.StringVar,
    width: int = 18,
    span: int = 1,
    browse: str | None = None,
) -> None:
    tk.Label(parent, text=label, bg=COLOR_PANEL, fg=COLOR_INK, font=FONT_SMALL).grid(
        row=row,
        column=column,
        sticky="w",
        padx=(0, 6),
        pady=4,
    )
    tk.Entry(
        parent,
        textvariable=variable,
        width=width,
        bg="#fffdf7",
        fg=COLOR_INK,
        relief="solid",
        bd=1,
        font=FONT_SMALL,
    ).grid(row=row, column=column + 1, columnspan=span, sticky="ew", padx=(0, 8), pady=4)
    if browse:
        tk.Button(
            parent,
            text="찾기",
            command=lambda: browse_file(variable, browse),
            bg="#e8decc",
            fg=COLOR_INK,
            activebackground="#ded1bd",
            relief="flat",
            padx=8,
            pady=3,
            font=FONT_SMALL,
        ).grid(row=row, column=column + 1 + span, sticky="w", pady=4)


def combo(
    parent: tk.Misc,
    row: int,
    column: int,
    label: str,
    variable: tk.StringVar,
    values: tuple[str, ...],
) -> None:
    tk.Label(parent, text=label, bg=COLOR_PANEL, fg=COLOR_INK, font=FONT_SMALL).grid(
        row=row,
        column=column,
        sticky="w",
        padx=(0, 6),
        pady=4,
    )
    ttk.Combobox(parent, textvariable=variable, values=values, width=10, state="readonly").grid(
        row=row,
        column=column + 1,
        sticky="w",
        padx=(0, 12),
        pady=4,
    )


def browse_file(variable: tk.StringVar, mode: str) -> None:
    if mode == "save":
        selected = filedialog.asksaveasfilename(
            title="파일 저장 위치 선택",
            defaultextension=".jsonl",
            filetypes=(("JSON Lines", "*.jsonl"), ("All files", "*.*")),
        )
    else:
        selected = filedialog.askopenfilename(
            title="파일 선택",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
    if selected:
        variable.set(selected)


def _wrapped_label(parent: tk.Misc, text: str, color: str) -> tk.Label:
    return tk.Label(
        parent,
        text=text,
        bg=COLOR_PANEL,
        fg=color,
        font=FONT_SMALL,
        wraplength=460,
        justify="left",
    )
