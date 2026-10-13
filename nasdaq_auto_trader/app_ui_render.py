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
from .operating_feedback import operating_wait_lines
from .daily_report_models import DailyReportResult
from .selection_presenter import selection_report_lines, selection_report_summary
from .quant_data.resources import application_data_root
from .unattended_policy import is_recoverable_preorder_failure


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
        if self.controller.state == "paused" and self.controller.last_error:
            self.status_var.set(
                f"자동매매 안전정지: {human_reason(self.controller.last_error)}"
            )
        elif _has_recoverable_retry(self.controller):
            self.status_var.set(
                f"자동운영 재시도 예약: {human_reason(self.controller.last_error)}"
            )
        elif self.controller.selection_error:
            self.status_var.set(self.controller.selection_error)
        else:
            self.status_var.set(f"보유현황 갱신 완료 ({len(snapshot.positions)}개)")

    def _render_auto_results(self, results: list[EngineResult] | None) -> None:
        if results is None:
            self.status_var.set("자동매매 대기")
            return
        learning = getattr(self.controller, "last_automatic_learning_result", None)
        if learning is not None:
            self._append_log("[자동 장외 학습]")
            self._render_learning_result(learning)
            next_run = self.controller.next_run_at
            if next_run is not None:
                self._append_log(
                    f"다음 자동운영: {next_run.astimezone():%Y-%m-%d %H:%M:%S}"
                )
            if self.controller.last_error:
                message = human_reason(self.controller.last_error)
                if _has_recoverable_retry(self.controller):
                    message = f"자동운영 재시도 예약: {message}"
                elif self.controller.state == "paused":
                    message = f"자동매매 안전정지: {message}"
                self.status_var.set(message)
                self._append_log(message)
            return
        wait_lines = operating_wait_lines(
            getattr(self.controller, "last_operating_transition", None),
            getattr(self.controller, "last_strategy_resolution", None),
        ) if not results else ()
        for line in wait_lines:
            self._append_log(line)
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
        shadow = getattr(self.controller, "last_shadow_scan", None)
        if shadow is not None:
            self.status_var.set(
                f"장중 무주문 스캔 완료 ({len(shadow.eligible_symbols)}/{len(shadow.scanned_symbols)}개 통과)"
            )
            self._append_log(
                f"장중 무주문 스캔: {len(shadow.scanned_symbols)}개 검토, "
                f"{len(shadow.eligible_symbols)}개 통과, 실제 주문 0건"
            )
            self._append_log(f"스캔 보고서: {shadow.report_path}")
        if self.controller.state == "paused" and self.controller.last_error:
            message = f"자동매매 안전정지: {human_reason(self.controller.last_error)}"
            if self.controller.last_error.startswith("learning_history_"):
                message = f"자동매매 안전정지: 학습 데이터 수집 차단 [{self.controller.last_error}]"
            self.status_var.set(message)
            self._append_log(message)
        elif _has_recoverable_retry(self.controller):
            message = f"자동운영 재시도 예약: {human_reason(self.controller.last_error)}"
            self.status_var.set(message)
            self._append_log(message)
        elif self.controller.selection_error:
            self.status_var.set(self.controller.selection_error)
        elif shadow is not None:
            self.status_var.set(
                f"장중 무주문 스캔 완료 ({len(shadow.eligible_symbols)}/{len(shadow.scanned_symbols)}개 통과)"
            )
        elif wait_lines:
            self.status_var.set(wait_lines[0])
        else:
            self.status_var.set(f"자동매매 1회 실행 완료 ({len(results)}개 종목)")
            if not results:
                self._append_log("자동운영 1회 실행 완료: 매매 결과 0개, 다음 주기 대기")
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
        for diagnostic in result.data_diagnostics:
            self._append_log(f"학습 데이터: {diagnostic}")
        if result.accepted_candidates == 0:
            self._append_log(
                "이번 학습에서 새로 검증을 통과한 모의운영 후보는 없습니다."
            )
        else:
            self._append_log(
                f"모의운영 후보 {result.accepted_candidates}개 등록 완료. "
                "실거래에는 모의운영 성과 검증과 별도 승인이 필요합니다."
            )

    def _render_daily_report(self, result: DailyReportResult) -> None:
        self.status_var.set(f"전일 보고서 생성 완료 ({result.market_date})")
        self._append_log(
            f"전일 보고서: {result.path} | 제출 {result.submitted_orders}건, "
            f"차단 {result.blocked_orders}건"
        )

    def _render_mode(self) -> None:
        config = self.controller.config
        settings = self.controller.trading_settings
        mode_label = _mode_label(config.mode)
        symbol_mode = (
            "AI 자동 선택"
            if settings.auto_symbol_selection_enabled
            else settings.ticker
        )
        safety = (
            "실거래 활성화 | 환경 승인·현금·주문 안전 잠금이 적용됩니다."
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
        config_name = Path(self.config_path).name
        self.mode_var.set(
            f"AI 완전자동 | 구성: {config_name} | 모드: {mode_label} | "
            f"브로커: {config.broker} | 종목: {symbol_mode}"
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
        self.report_button.configure(state="disabled" if busy else "normal")


def _learning_status_text(status: str) -> str:
    labels = {
        "completed": "상태: 완료",
        "aborted": "상태: 중단",
        "blocked": "상태: 차단",
    }
    return labels.get(status, "상태: 확인 필요")


def _has_recoverable_retry(controller) -> bool:
    reason = controller.last_error
    return bool(
        controller.state == "running"
        and reason
        and controller.trading_settings.unattended_operation_enabled
        and is_recoverable_preorder_failure(reason)
    )
