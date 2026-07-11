from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from nasdaq_auto_trader.ai_quant_lab.operator_gui_controls import action_row, combo, field, panel
from nasdaq_auto_trader.ai_quant_lab.operator_gui_presenter import operator_action_cards
from nasdaq_auto_trader.ai_quant_lab.operator_gui_theme import (
    COLOR_BG,
    COLOR_BORDER,
    COLOR_HEADER,
    COLOR_INK,
    COLOR_MUTED,
    COLOR_PANEL,
    COLOR_WARNING,
    FONT_BODY,
    FONT_DISPLAY,
    FONT_MONO,
    FONT_SMALL,
    FONT_TITLE,
)


def build_operator_ui(app) -> None:
    app.root.configure(bg=COLOR_BG)
    app.root.columnconfigure(0, weight=1)
    app.root.rowconfigure(3, weight=1)
    _create_variables(app)
    _build_header(app)
    _build_status_panel(app)
    _build_workflow_area(app)
    _build_output_panel(app)


def _create_variables(app) -> None:
    app.strategy_id_var = tk.StringVar(value="manual-gui-probe")
    app.strategy_version_var = tk.StringVar(value="v1")
    app.symbol_var = tk.StringVar(value="QQQ")
    app.price_var = tk.StringVar(value="100")
    app.side_var = tk.StringVar(value="buy")
    app.mode_var = tk.StringVar(value="paper")
    app.ledger_var = tk.StringVar(value="data/ai_quant_lab/gui_paper_shadow.jsonl")
    app.candidate_var = tk.StringVar(value="")
    app.rollback_reason_var = tk.StringVar(value="operator_manual_no_trade_rollback")


def _build_header(app) -> None:
    header = tk.Frame(app.root, bg=COLOR_HEADER, padx=20, pady=16)
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(1, weight=1)
    tk.Label(
        header,
        text="AI Quant Lab Safe Operator Console",
        bg=COLOR_HEADER,
        fg="#f8f4e8",
        font=FONT_DISPLAY,
    ).grid(row=0, column=0, sticky="w")
    tk.Label(
        header,
        text="비개발자용 운영 콘솔. 이 GUI에는 실주문 실행 버튼이 없습니다.",
        bg=COLOR_HEADER,
        fg="#cfe3d9",
        font=FONT_BODY,
    ).grid(row=1, column=0, sticky="w", pady=(4, 0))
    app.status_var = tk.StringVar(value="대기")
    tk.Label(
        header,
        textvariable=app.status_var,
        bg="#245746",
        fg="#f8f4e8",
        font=FONT_TITLE,
        padx=14,
        pady=8,
    ).grid(row=0, column=1, rowspan=2, sticky="e")


def _build_status_panel(app) -> None:
    status_panel = panel(app.root, row=1, title="현재 안전 상태")
    status_panel.columnconfigure(1, weight=1)
    app.badge_var = tk.StringVar(value="확인 중")
    app.badge_label = tk.Label(
        status_panel,
        textvariable=app.badge_var,
        bg=COLOR_WARNING,
        fg="#ffffff",
        font=FONT_TITLE,
        padx=14,
        pady=10,
    )
    app.badge_label.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 14))
    app.headline_var = tk.StringVar(value="상태를 확인하고 있습니다.")
    app.detail_var = tk.StringVar(value="")
    tk.Label(
        status_panel,
        textvariable=app.headline_var,
        bg=COLOR_PANEL,
        fg=COLOR_INK,
        font=FONT_TITLE,
    ).grid(row=0, column=1, sticky="w")
    tk.Label(
        status_panel,
        textvariable=app.detail_var,
        bg=COLOR_PANEL,
        fg=COLOR_MUTED,
        font=FONT_BODY,
        wraplength=780,
        justify="left",
    ).grid(row=1, column=1, sticky="w", pady=(4, 0))
    _build_checklist(app, status_panel)


def _build_checklist(app, status_panel: tk.Misc) -> None:
    checklist = tk.Frame(status_panel, bg=COLOR_PANEL)
    checklist.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
    app.checklist_vars = [tk.StringVar(value="-") for _ in range(5)]
    for index, variable in enumerate(app.checklist_vars):
        tk.Label(
            checklist,
            textvariable=variable,
            bg=COLOR_PANEL,
            fg=COLOR_INK,
            font=FONT_SMALL,
            anchor="w",
        ).grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 24), pady=2)
    checklist.columnconfigure(0, weight=1)
    checklist.columnconfigure(1, weight=1)


def _build_workflow_area(app) -> None:
    main = tk.Frame(app.root, bg=COLOR_BG)
    main.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
    main.columnconfigure(0, weight=1)
    main.columnconfigure(1, weight=1)
    actions = _label_frame(main, "운영 절차")
    actions.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    actions.columnconfigure(0, weight=1)
    for index, card in enumerate(operator_action_cards()):
        action_row(
            actions,
            index,
            card.key,
            card.title,
            card.description,
            card.safety_note,
            app._action_command(card.key),
        )
    inputs = _label_frame(main, "운영 입력값")
    inputs.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
    _build_inputs(app, inputs)


def _build_inputs(app, inputs: tk.Misc) -> None:
    inputs.columnconfigure(1, weight=1)
    inputs.columnconfigure(3, weight=1)
    field(inputs, 0, 0, "전략 ID", app.strategy_id_var)
    field(inputs, 0, 2, "버전", app.strategy_version_var, width=10)
    field(inputs, 1, 0, "심볼", app.symbol_var, width=10)
    field(inputs, 1, 2, "가격", app.price_var, width=10)
    combo(inputs, 2, 0, "매수/매도", app.side_var, ("buy", "sell"))
    combo(inputs, 2, 2, "실험 모드", app.mode_var, ("paper", "shadow"))
    field(inputs, 3, 0, "페이퍼 장부 파일", app.ledger_var, span=3, browse="save")
    field(inputs, 4, 0, "후보 JSON 파일", app.candidate_var, span=3, browse="open")
    field(inputs, 5, 0, "롤백 사유", app.rollback_reason_var, span=3)
    _build_paths(app, inputs, row=6)


def _build_paths(app, inputs: tk.Misc, row: int) -> None:
    paths = tk.LabelFrame(inputs, text="사용 중인 운영 파일", bg=COLOR_PANEL, fg=COLOR_INK, font=FONT_SMALL)
    paths.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(12, 0), padx=10)
    paths.columnconfigure(1, weight=1)
    items = (
        ("AI 설정", app.controller.paths.ai_config_path),
        ("전략 등록소", app.controller.paths.registry_path),
        ("승격 전략", app.controller.paths.promoted_path),
        ("감사 로그", app.controller.paths.audit_log_path),
    )
    for index, (label, value) in enumerate(items):
        tk.Label(paths, text=label, bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL).grid(
            row=index,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=1,
        )
        tk.Label(paths, text=_path_text(value), bg=COLOR_PANEL, fg=COLOR_INK, font=FONT_SMALL).grid(
            row=index,
            column=1,
            sticky="w",
            pady=1,
        )


def _build_output_panel(app) -> None:
    output_frame = _label_frame(app.root, "결과와 원문 JSON")
    output_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 16))
    output_frame.rowconfigure(0, weight=1)
    output_frame.columnconfigure(0, weight=1)
    app.output_text = tk.Text(
        output_frame,
        wrap="word",
        height=14,
        state="disabled",
        bg="#101820",
        fg="#eef3ed",
        insertbackground="#eef3ed",
        relief="flat",
        padx=12,
        pady=12,
        font=FONT_MONO,
    )
    app.output_text.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(output_frame, orient="vertical", command=app.output_text.yview)
    app.output_text.configure(yscrollcommand=scrollbar.set)
    scrollbar.grid(row=0, column=1, sticky="ns")


def _label_frame(parent: tk.Misc, text: str) -> tk.LabelFrame:
    return tk.LabelFrame(
        parent,
        text=text,
        bg=COLOR_PANEL,
        fg=COLOR_INK,
        font=FONT_TITLE,
        padx=12,
        pady=10,
        highlightbackground=COLOR_BORDER,
        highlightthickness=1,
    )


def _path_text(value: Path | None) -> str:
    return value.as_posix() if value else "(default)"
