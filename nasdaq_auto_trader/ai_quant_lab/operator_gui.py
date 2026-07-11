from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Callable

from nasdaq_auto_trader.ai_quant_lab.operator_gui_controller import (
    AIQuantGuiController,
    parse_paper_mode,
    parse_trade_side,
    pretty_payload,
)
from nasdaq_auto_trader.ai_quant_lab.operator_gui_layout import build_operator_ui
from nasdaq_auto_trader.ai_quant_lab.operator_gui_models import (
    OperatorGuiInputError,
    OperatorGuiResult,
)
from nasdaq_auto_trader.ai_quant_lab.operator_gui_presenter import (
    gui_result_explanation,
    gui_status_view,
)
from nasdaq_auto_trader.ai_quant_lab.operator_gui_theme import BADGE_COLORS, configure_style
from nasdaq_auto_trader.ai_quant_lab.operator_models import (
    OperatorPaths,
    UnsupportedCommandError,
)


class AIQuantOperatorApp:
    def __init__(self, root: tk.Tk, controller: AIQuantGuiController) -> None:
        self.root = root
        self.controller = controller
        self.root.title("AI Quant Lab Safe Operator Console")
        self.root.geometry("1180x960")
        self.root.minsize(1040, 760)
        self._build_ui()
        self._render_result(self.controller.status())

    def _build_ui(self) -> None:
        configure_style(self.root)
        build_operator_ui(self)

    def _action_command(self, key: str) -> Callable[[], None]:
        commands: dict[str, Callable[[], None]] = {
            "status": self._run_status,
            "nightly": self._run_nightly,
            "champion-lock": self._run_champion_lock,
            "paper-shadow": self._run_paper_shadow,
            "rollback": self._run_rollback,
            "live-guard": self._run_live_guard_check,
        }
        return commands[key]

    def _run_status(self) -> None:
        self._run_action(self.controller.status)

    def _run_nightly(self) -> None:
        if not self._confirm(
            "연구/전략 생성 확인",
            "전략 후보 생성은 등록소와 감사 로그를 변경할 수 있습니다.\n설정 파일의 리서치 명령만 사용합니다. 계속할까요?",
        ):
            return
        self._run_action(
            lambda: self.controller.nightly(
                insane_search_command=(),
                candidate_json=_optional_path(self.candidate_var.get()),
            )
        )

    def _run_champion_lock(self) -> None:
        if not self._confirm(
            "챔피언 잠금 확인",
            "선택한 전략 ID와 버전을 배포 후보로 잠급니다.\n실주문은 보내지 않지만 운영 상태가 바뀝니다. 계속할까요?",
        ):
            return
        self._run_action(
            lambda: self.controller.champion_lock(
                self.strategy_id_var.get(),
                self.strategy_version_var.get(),
            )
        )

    def _run_rollback(self) -> None:
        if not self._confirm(
            "긴급 no-trade 롤백 확인",
            "현재 승격 전략을 no-trade 상태로 되돌립니다.\n방어용 변경이며 감사 로그에 기록됩니다. 계속할까요?",
        ):
            return
        self._run_action(lambda: self.controller.rollback(self.rollback_reason_var.get()))

    def _run_paper_shadow(self) -> None:
        if not self._confirm(
            "페이퍼/섀도우 리허설 확인",
            "가상 체결을 만들고 페이퍼 장부와 감사 로그를 기록할 수 있습니다.\n실주문은 보내지 않습니다. 계속할까요?",
        ):
            return
        self._run_action(
            lambda: self.controller.paper_shadow(
                ledger_path=_optional_path(self.ledger_var.get()),
                strategy_id=self.strategy_id_var.get(),
                strategy_version=self.strategy_version_var.get(),
                symbol=self.symbol_var.get(),
                side=parse_trade_side(self.side_var.get()),
                price=_positive_float(self.price_var.get(), "price"),
                mode=parse_paper_mode(self.mode_var.get()),
                equity=100_000.0,
                cash=100_000.0,
            )
        )

    def _run_live_guard_check(self) -> None:
        self._run_action(self.controller.status)

    def _run_action(self, action: Callable[[], OperatorGuiResult]) -> None:
        self.status_var.set("실행 중")
        try:
            result = action()
        except (OSError, RuntimeError, OperatorGuiInputError, UnsupportedCommandError) as exc:
            self.status_var.set("오류: 입력값 또는 파일 확인 필요")
            self._write_output(f"오류\n{exc}")
            messagebox.showerror("AI Quant Lab", str(exc))
            return
        self._render_result(result)

    def _render_result(self, result: OperatorGuiResult) -> None:
        status = "완료" if result.exit_code == 0 else "차단"
        action_label = gui_result_explanation(result)[0].replace("작업: ", "", 1)
        self.status_var.set(f"{status}: {action_label}")
        if result.action == "status":
            self._render_status_card(result)
        else:
            self._refresh_status_card()
        plain_text = "\n".join(gui_result_explanation(result))
        self._write_output(f"{plain_text}\n\n기계 판독용 원문 JSON\n{pretty_payload(result.payload)}")

    def _render_status_card(self, result: OperatorGuiResult) -> None:
        view = gui_status_view(result)
        self.badge_var.set(view.badge_text)
        self.badge_label.configure(bg=BADGE_COLORS[view.badge_level])
        self.headline_var.set(view.headline)
        self.detail_var.set(view.detail)
        for index, variable in enumerate(self.checklist_vars):
            variable.set(f"- {view.checklist[index]}" if index < len(view.checklist) else "-")

    def _refresh_status_card(self) -> None:
        try:
            self._render_status_card(self.controller.status())
        except (OSError, RuntimeError, OperatorGuiInputError, UnsupportedCommandError) as exc:
            self._render_status_error(exc)

    def _render_status_error(
        self,
        exc: OSError | RuntimeError | OperatorGuiInputError | UnsupportedCommandError,
    ) -> None:
        self.badge_var.set("상태 확인 실패")
        self.badge_label.configure(bg=BADGE_COLORS["blocked"])
        self.headline_var.set("최신 안전 상태를 확인하지 못했습니다.")
        self.detail_var.set(str(exc))
        for index, variable in enumerate(self.checklist_vars):
            variable.set("- 상태 새로고침을 다시 실행하세요." if index == 0 else "-")

    def _write_output(self, value: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("end", value)
        self.output_text.configure(state="disabled")

    def _confirm(self, title: str, message: str) -> bool:
        return bool(messagebox.askyesno(title, message))


def launch_operator_gui(paths: OperatorPaths) -> int:
    root = tk.Tk()
    AIQuantOperatorApp(root, AIQuantGuiController(paths))
    root.mainloop()
    return 0


def _optional_path(value: str) -> Path | None:
    text = value.strip()
    return Path(text) if text else None


def _positive_float(value: str, label: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise OperatorGuiInputError(f"{label} must be a number") from exc
    if number <= 0:
        raise OperatorGuiInputError(f"{label} must be greater than zero")
    return number
