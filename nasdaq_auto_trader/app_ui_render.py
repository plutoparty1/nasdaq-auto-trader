from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .app_format import (
    _format_currency,
    _format_number,
    _format_optional_currency,
    _format_optional_pct,
    _mode_label,
    _summarize_trade_result,
)
from .app_types import EngineResult, PortfolioSnapshot
from .ai_quant_lab.operator_gui_presenter import human_reason
from .learning_runner import LearningRunResult
from .selection_presenter import selection_report_lines, selection_report_summary
from .quant_data.resources import application_data_root


class DashboardRenderMixin:
    def _render_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        self.cash_var.set(f"Cash: {_format_currency(snapshot.account.cash)}")
        self.equity_var.set(f"Equity: {_format_currency(snapshot.account.equity)}")
        self.buying_power_var.set(f"Buying Power: {_format_currency(snapshot.account.buying_power)}")
        self.updated_var.set(f"Updated: {snapshot.as_of.astimezone().strftime('%Y-%m-%d %H:%M:%S')}")

        for item_id in self.positions_tree.get_children():
            self.positions_tree.delete(item_id)
        for position in sorted(snapshot.positions, key=lambda item: item.symbol):
            self.positions_tree.insert(
                "",
                "end",
                values=(
                    position.symbol,
                    _format_number(position.qty),
                    _format_currency(position.avg_entry_price),
                    _format_optional_currency(position.latest_price),
                    _format_currency(position.market_value),
                    _format_optional_currency(position.unrealized_pl),
                    _format_optional_pct(position.unrealized_pl_pct),
                ),
            )
        if not snapshot.positions:
            self.positions_tree.insert("", "end", values=("보유 없음", "", "", "", "", "", ""))
        if self.controller.selection_error:
            self.status_var.set(self.controller.selection_error)
        else:
            self.status_var.set(f"보유현황 갱신 완료 ({len(snapshot.positions)}개)")

    def _render_auto_results(self, results: list[EngineResult] | None) -> None:
        if results is None:
            self.status_var.set("자동매매 대기")
            return
        report = (
            self.controller.last_selection_report
            if self.controller.trading_settings.auto_symbol_selection_enabled
            else None
        )
        if report is not None:
            self.selection_var.set(selection_report_summary(report))
            self._append_log("[자동 종목 선택]")
            for line in selection_report_lines(report):
                self._append_log(f"  {line}")
        if self.controller.selection_error:
            self.status_var.set(self.controller.selection_error)
        else:
            self.status_var.set(f"자동매매 1회 실행 완료 ({len(results)}개 종목)")
        for item in results:
            self._append_log(_summarize_trade_result(item))

    def _render_learning_result(self, result: LearningRunResult) -> None:
        label = "학습 완료" if result.status == "completed" else "학습 중단"
        self.status_var.set(label)
        self._append_log(f"{label}: {_learning_status_text(result.status)}")
        self._append_log(f"학습 저장소: {result.artifact_root}")
        self._append_log(f"생성 후보: {result.generated_candidates}개")
        self._append_log(f"검증 통과 후보: {result.accepted_candidates}개")
        self._append_log(f"제출된 실제 주문: {result.submitted_orders}건")
        if result.reasons:
            self._append_log("학습 결과 사유:")
            for reason in result.reasons:
                self._append_log(f"  {human_reason(reason)}")
        if result.accepted_candidates == 0:
            self._append_log(
                "자동 선택에 사용할 학습 완료 전략은 아직 없습니다. "
                "후보 전략과 시장 데이터가 검증을 통과해야 자동 선택이 켜집니다."
            )

    def _render_mode(self) -> None:
        config = self.controller.config
        settings = self.controller.trading_settings
        mode_label = _mode_label(config.mode)
        symbol_mode = (
            "과거 데이터 자동 선택"
            if settings.auto_symbol_selection_enabled
            else settings.ticker
        )
        safety = (
            "실주문 차단 | 실거래 설정 감지: 데스크톱의 모든 실행이 차단됩니다."
            if config.mode == "live"
            else f"실주문 차단 | 데스크톱 안전 모드: {mode_label}"
        )
        self.warning_var.set(safety)
        if settings.auto_symbol_selection_enabled:
            report = self.controller.last_selection_report
            summary = (
                selection_report_summary(report)
                if report is not None
                else "자동 종목 선택 | 다음 주기 대기"
            )
            self.selection_var.set(summary)
        else:
            self.selection_var.set(f"수동 종목 모드 | {settings.ticker}")
        self.mode_var.set(
            f"Config: {self.config_path} | GUI Config: {self.controller.settings_path} | "
            f"Mode: {mode_label} | Broker: {config.broker} | Symbol: {symbol_mode}"
        )
        self._append_log(f"현재 모드: {mode_label} / 종목: {symbol_mode}")

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self._append_log_file(line)

    def _append_log_file(self, line: str) -> None:
        settings = self.controller.trading_settings
        if not settings.save_log:
            return
        try:
            log_path = Path(settings.log_path)
            if not log_path.is_absolute():
                log_path = application_data_root() / log_path
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as file:
                file.write(line)
        except OSError:
            return

    def _update_controls(self) -> None:
        state = self.controller.state
        busy = self._worker is not None
        progress = self.controller.last_learning_progress
        if busy and progress is not None:
            self.status_var.set(f"학습 {progress.percent}% · {progress.stage}")
        self.start_button.configure(state="disabled" if busy or state == "running" else "normal")
        self.pause_button.configure(state="normal" if state == "running" else "disabled")
        self.resume_button.configure(state="normal" if not busy and state == "paused" else "disabled")
        self.refresh_button.configure(state="disabled" if busy else "normal")
        self.learning_button.configure(state="disabled" if busy else "normal")
        self.cancel_learning_button.configure(state="normal" if busy else "disabled")
        self.settings_button.configure(state="disabled" if busy else "normal")


def _learning_status_text(status: str) -> str:
    labels = {
        "completed": "상태: 완료",
        "aborted": "상태: 중단",
        "blocked": "상태: 차단",
    }
    return labels.get(status, "상태: 확인 필요")
