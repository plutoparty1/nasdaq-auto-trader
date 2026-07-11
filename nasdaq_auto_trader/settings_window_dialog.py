from __future__ import annotations

from pathlib import Path
from typing import Callable

from .config_manager import (
    SettingsError,
    TradingSettings,
    load_or_create_settings,
    save_settings,
    settings_from_dict,
    validate_settings,
)
from .settings_window_fields import SETTINGS_SECTIONS
from .gui_theme import MUTED, apply_operator_theme


VALIDATION_MESSAGES = {
    "ai_max_order_qty must be less than or equal to max_position_qty": (
        "AI 최대 주문 수량은 최대 보유 수량보다 작거나 같아야 합니다."
    ),
}


class SettingsWindow:
    """A modal Tkinter settings editor."""

    def __init__(
        self,
        parent,
        settings: TradingSettings,
        settings_path: str | Path,
        on_save: Callable[[TradingSettings], None] | None = None,
    ) -> None:
        import tkinter as tk
        from tkinter import messagebox, ttk

        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.settings_path = Path(settings_path)
        self.on_save = on_save
        self.variables = {}
        self.widgets = {}

        self.window = tk.Toplevel(parent)
        self.window.title("자동매매 설정")
        self.window.geometry("980x760")
        self.window.minsize(860, 580)
        self.window.transient(parent)
        self.window.grab_set()
        apply_operator_theme(self.window, self.ttk)

        self._build_ui()
        self._load_into_variables(settings)

    def _build_ui(self) -> None:
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)

        outer = self.ttk.Frame(self.window, padding=10)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        intro = self.ttk.Label(
            outer,
            text=(
                "어려운 설정은 기본값 그대로 두고, 종목과 수량부터 바꿔도 됩니다. "
                "실제 돈으로 거래하려면 연습 모드를 끄고 실거래를 켜야 하며, 저장 전 경고를 꼭 확인하세요."
            ),
            wraplength=900,
        )
        intro.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        canvas = self.tk.Canvas(outer, highlightthickness=0)
        scrollbar = self.ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.form = self.ttk.Frame(canvas)
        self.form.columnconfigure(0, weight=1)
        self.form.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        form_window = canvas.create_window((0, 0), window=self.form, anchor="nw")
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(form_window, width=event.width),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")

        row = 0
        for section, fields in SETTINGS_SECTIONS:
            section_frame = self.ttk.LabelFrame(self.form, text=section, padding=8)
            section_frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
            section_frame.columnconfigure(1, weight=1)
            section_frame.columnconfigure(2, weight=2)
            row += 1
            for field_row, (name, label, kind, help_text) in enumerate(fields):
                self.ttk.Label(section_frame, text=label).grid(
                    row=field_row,
                    column=0,
                    sticky="w",
                    padx=(0, 8),
                    pady=3,
                )
                if kind == "bool":
                    variable = self.tk.BooleanVar()
                    widget = self.ttk.Checkbutton(section_frame, variable=variable)
                else:
                    variable = self.tk.StringVar()
                    widget = self.ttk.Entry(section_frame, textvariable=variable)
                widget.grid(row=field_row, column=1, sticky="ew", pady=3)
                self.ttk.Label(
                    section_frame,
                    text=help_text,
                    wraplength=420,
                    foreground=MUTED,
                ).grid(row=field_row, column=2, sticky="w", padx=(12, 0), pady=3)
                self.variables[name] = variable
                self.widgets[name] = widget

        auto_variable = self.variables["auto_symbol_selection_enabled"]
        auto_variable.trace_add("write", self._sync_auto_symbol_widgets)

        buttons = self.ttk.Frame(outer)
        buttons.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        buttons.columnconfigure(0, weight=1)
        self.ttk.Button(buttons, text="입력값 확인", command=self._validate_current).grid(
            row=0,
            column=1,
            padx=(0, 6),
        )
        self.ttk.Button(buttons, text="저장된 설정 다시 불러오기", command=self._load_current).grid(
            row=0,
            column=2,
            padx=(0, 6),
        )
        self.ttk.Button(buttons, text="처음 값으로 되돌리기", command=self._reset_defaults).grid(
            row=0,
            column=3,
            padx=(0, 6),
        )
        self.ttk.Button(buttons, text="취소", command=self.window.destroy).grid(
            row=0,
            column=4,
            padx=(0, 6),
        )
        self.ttk.Button(buttons, text="저장", command=self._save).grid(row=0, column=5)

    def _load_into_variables(self, settings: TradingSettings) -> None:
        values = settings.to_dict()
        for name, variable in self.variables.items():
            value = values[name]
            variable.set(
                _settings_variable_value(
                    value,
                    is_boolean=isinstance(variable, self.tk.BooleanVar),
                )
            )
        self._sync_auto_symbol_widgets()

    def _sync_auto_symbol_widgets(self, *_args) -> None:
        enabled = bool(self.variables["auto_symbol_selection_enabled"].get())
        state = "disabled" if enabled else "normal"
        self.widgets["ticker"].configure(state=state)
        self.widgets["ai_candidate_tickers"].configure(state=state)

    def _read_settings(self) -> TradingSettings:
        raw = {}
        for name, variable in self.variables.items():
            raw[name] = variable.get()
        return settings_from_dict(raw)

    def _validate_current(self) -> bool:
        try:
            settings = self._read_settings()
        except (TypeError, ValueError) as exc:
            self.messagebox.showerror("입력 오류", str(exc), parent=self.window)
            return False
        result = validate_settings(settings)
        if result.errors:
            self.messagebox.showerror(
                "고쳐야 할 설정",
                localized_validation_message(result.errors),
                parent=self.window,
            )
            return False
        if result.warnings:
            self.messagebox.showwarning(
                "주의할 설정",
                "\n".join(result.warnings),
                parent=self.window,
            )
        else:
            self.messagebox.showinfo("확인 완료", "설정값에 문제가 없습니다.", parent=self.window)
        return True

    def _save(self) -> None:
        try:
            settings = self._read_settings()
        except (TypeError, ValueError) as exc:
            self.messagebox.showerror("입력 오류", str(exc), parent=self.window)
            return

        result = validate_settings(settings)
        if result.errors:
            self.messagebox.showerror(
                "고쳐야 할 설정",
                localized_validation_message(result.errors),
                parent=self.window,
            )
            return
        if result.warnings:
            proceed = self.messagebox.askyesno(
                "주의할 설정",
                "\n".join(result.warnings) + "\n\n이대로 저장할까요?",
                parent=self.window,
            )
            if not proceed:
                return

        try:
            save_settings(settings, self.settings_path)
        except (OSError, SettingsError) as exc:
            self.messagebox.showerror("저장 실패", str(exc), parent=self.window)
            return
        if self.on_save is not None:
            self.on_save(settings)
        self.messagebox.showinfo("저장 완료", "설정이 저장되었습니다.", parent=self.window)
        self.window.destroy()

    def _load_current(self) -> None:
        try:
            settings = load_or_create_settings(self.settings_path)
        except (OSError, SettingsError) as exc:
            self.messagebox.showerror("불러오기 실패", str(exc), parent=self.window)
            return
        self._load_into_variables(settings)

    def _reset_defaults(self) -> None:
        self._load_into_variables(TradingSettings())


def open_settings_window(
    parent,
    settings: TradingSettings,
    settings_path: str | Path,
    on_save: Callable[[TradingSettings], None] | None = None,
) -> SettingsWindow:
    """Open the settings editor and return the window wrapper."""

    return SettingsWindow(parent, settings, settings_path, on_save=on_save)


def _settings_variable_value(value, is_boolean: bool):
    if is_boolean:
        return bool(value)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def localized_validation_message(errors: list[str]) -> str:
    return "\n".join(VALIDATION_MESSAGES.get(error, error) for error in errors)
