from __future__ import annotations

from .gui_theme import DEEP_GREEN, PAPER_RAISED


class DashboardLayoutMixin:
    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(4, weight=1)

        header = self.ttk.Frame(
            self.root,
            padding=(12, 10, 12, 10),
            style="Header.TFrame",
        )
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        self.ttk.Label(
            header,
            text="NASDAQ Auto Trader",
            style="HeaderTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        self.status_var = self.tk.StringVar(value="대기")
        self.ttk.Label(
            header,
            textvariable=self.status_var,
            style="HeaderStatus.TLabel",
        ).grid(row=0, column=1, sticky="e")

        self.warning_var = self.tk.StringVar(value="")
        self.warning_label = self.tk.Label(
            self.root,
            textvariable=self.warning_var,
            bg=DEEP_GREEN,
            fg="white",
            anchor="w",
            padx=12,
            pady=6,
            font=("Aptos", 10, "bold"),
        )
        self.warning_label.grid(row=1, column=0, sticky="ew")

        self.selection_var = self.tk.StringVar(value="AI 종목 선택: 대기")
        self.ttk.Label(
            self.root,
            textvariable=self.selection_var,
            style="Selection.TLabel",
        ).grid(row=2, column=0, sticky="ew")

        details = self.ttk.Frame(self.root, padding=(12, 0, 12, 8))
        details.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        details.columnconfigure(4, weight=1)

        self.cash_var = self.tk.StringVar(value="Cash: -")
        self.equity_var = self.tk.StringVar(value="Equity: -")
        self.buying_power_var = self.tk.StringVar(value="Buying Power: -")
        self.updated_var = self.tk.StringVar(value="Updated: -")
        for index, variable in enumerate(
            [self.cash_var, self.equity_var, self.buying_power_var, self.updated_var]
        ):
            self.ttk.Label(details, textvariable=variable).grid(
                row=0,
                column=index,
                padx=(0, 16),
                sticky="w",
            )

        main = self.ttk.Frame(self.root, padding=(12, 0, 12, 8))
        main.grid(row=4, column=0, sticky="nsew")
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        left = self.ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        button_bar = self.ttk.Frame(left)
        button_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.start_button = self.ttk.Button(
            button_bar,
            text="자동매매 실행",
            command=self._start_auto_trading,
        )
        self.pause_button = self.ttk.Button(button_bar, text="정지", command=self._pause_auto_trading)
        self.resume_button = self.ttk.Button(button_bar, text="재개", command=self._resume_auto_trading)
        self.refresh_button = self.ttk.Button(
            button_bar,
            text="보유현황 새로고침",
            command=self._refresh_now,
        )
        self.learning_button = self.ttk.Button(
            button_bar,
            text="학습만 실행",
            command=self._start_learning_only,
        )
        self.cancel_learning_button = self.ttk.Button(
            button_bar,
            text="학습 취소",
            command=self._cancel_learning,
        )
        self.report_button = self.ttk.Button(
            button_bar,
            text="전일 보고서 열기",
            command=self._open_latest_report,
        )
        for index, button in enumerate(
            [
                self.start_button,
                self.pause_button,
                self.resume_button,
                self.refresh_button,
                self.learning_button,
                self.cancel_learning_button,
                self.report_button,
            ]
        ):
            button.grid(
                row=index // 4,
                column=index % 4,
                padx=(0, 6),
                pady=(0, 4),
                sticky="w",
            )

        columns = (
            "symbol",
            "qty",
            "avg_entry_price",
            "latest_price",
            "market_value",
            "unrealized_pl",
            "unrealized_pl_pct",
        )
        self.positions_tree = self.ttk.Treeview(left, columns=columns, show="headings", height=14)
        headings = {
            "symbol": "종목",
            "qty": "수량",
            "avg_entry_price": "평균단가",
            "latest_price": "현재가",
            "market_value": "평가금액",
            "unrealized_pl": "손익",
            "unrealized_pl_pct": "손익률",
        }
        widths = {
            "symbol": 55,
            "qty": 45,
            "avg_entry_price": 65,
            "latest_price": 65,
            "market_value": 75,
            "unrealized_pl": 65,
            "unrealized_pl_pct": 65,
        }
        for column in columns:
            self.positions_tree.heading(column, text=headings[column])
            self.positions_tree.column(
                column,
                width=widths[column],
                minwidth=40,
                anchor="e" if column != "symbol" else "w",
                stretch=True,
            )
        self.positions_tree.grid(row=1, column=0, sticky="nsew")
        scrollbar = self.ttk.Scrollbar(left, orient="vertical", command=self.positions_tree.yview)
        horizontal = self.ttk.Scrollbar(
            left,
            orient="horizontal",
            command=self.positions_tree.xview,
        )
        self.positions_tree.configure(
            yscrollcommand=scrollbar.set,
            xscrollcommand=horizontal.set,
        )
        scrollbar.grid(row=1, column=1, sticky="ns")
        horizontal.grid(row=2, column=0, sticky="ew")

        right = self.ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        self.ttk.Label(right, text="실행 로그").grid(row=0, column=0, sticky="w")
        self.log_text = self.tk.Text(
            right,
            height=16,
            wrap="word",
            state="disabled",
            background=PAPER_RAISED,
            font=("Cascadia Mono", 9),
        )
        self.log_text.grid(row=1, column=0, sticky="nsew")
        log_scrollbar = self.ttk.Scrollbar(right, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        log_scrollbar.grid(row=1, column=1, sticky="ns")

        footer = self.ttk.Frame(self.root, padding=(12, 0, 12, 10))
        footer.grid(row=5, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.mode_var = self.tk.StringVar(value="")
        self.ttk.Label(footer, textvariable=self.mode_var).grid(row=0, column=0, sticky="w")
