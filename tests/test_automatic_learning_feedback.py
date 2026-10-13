from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from nasdaq_auto_trader.ai_quant_lab.operator_gui_presenter import human_reason
from nasdaq_auto_trader.app_ui_render import DashboardRenderMixin
from nasdaq_auto_trader.learning_runner import LearningRunResult
from tests.test_operating_market_data_recovery import controller_at


class TextValue:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


def test_automatic_learning_displays_block_and_next_cycle(tmp_path: Path) -> None:
    # Given: an isolated scheduled learner rejects mismatched market dates.
    controller = controller_at(tmp_path, datetime(2026, 9, 8, tzinfo=timezone.utc))
    result = LearningRunResult(
        "blocked", 0, 0, ("market_data_timestamps_misaligned",), 0, tmp_path,
    )
    view = DashboardRenderMixin()
    view.controller = controller
    view.status_var = TextValue()
    logs: list[str] = []
    view._append_log = logs.append

    # When: a scheduled result reaches the same renderer used by the GUI queue.
    with patch.object(controller, "_execute_learning", return_value=result):
        view._render_auto_results(controller.run_operating_cycle(force=True))

    # Then: learning rejection and the next scheduled run are visible.
    assert any("학습" in line and "차단" in line for line in logs)
    assert any("날짜" in line for line in logs)
    assert any("다음 자동운영" in line for line in logs)
    assert controller.last_automatic_learning_result == result


def test_failed_next_cycle_clears_previous_learning_result(tmp_path: Path) -> None:
    # Given: the previous automatic learning result is still available to the UI.
    controller = controller_at(tmp_path, datetime(2026, 9, 8, tzinfo=timezone.utc))
    controller.last_automatic_learning_result = LearningRunResult(
        "completed", 1, 1, (), 0, tmp_path,
    )

    # When: the next scheduled cycle fails to retrieve market data.
    with patch.object(controller, "_execute_learning", side_effect=OSError("offline")):
        controller.run_operating_cycle(force=True)

    # Then: a stale success cannot mask the new failure.
    assert controller.last_automatic_learning_result is None


def test_empty_cycle_emits_one_heartbeat_without_learning_replay(tmp_path: Path) -> None:
    # Given: an automatic cycle did no trading and did not learn.
    controller = controller_at(tmp_path, datetime(2026, 9, 8, tzinfo=timezone.utc))
    view = DashboardRenderMixin()
    view.controller = controller
    view.status_var = TextValue()
    logs: list[str] = []
    view._append_log = logs.append

    # When: the scheduled callback renders the empty result.
    view._render_auto_results([])

    # Then: the user sees activity even though no orders were generated.
    assert sum("1회 실행 완료" in line for line in logs) == 1
    assert not any("학습 완료" in line for line in logs)


def test_learning_feedback_preserves_unrelated_retry_warning(tmp_path: Path) -> None:
    controller = controller_at(tmp_path, datetime(2026, 9, 8, tzinfo=timezone.utc))
    controller.last_error = "account_state_unavailable"
    controller.last_automatic_learning_result = LearningRunResult(
        "completed", 1, 1, (), 0, tmp_path,
    )
    view = DashboardRenderMixin()
    view.controller = controller
    view.status_var = TextValue()
    logs: list[str] = []
    view._append_log = logs.append

    view._render_auto_results([])

    assert "재시도" in view.status_var.value
    assert any("학습 완료" in line for line in logs)


def test_learning_feedback_reports_only_current_run_candidates(tmp_path: Path) -> None:
    view = DashboardRenderMixin()
    view.status_var = TextValue()
    logs: list[str] = []
    view._append_log = logs.append

    view._render_learning_result(LearningRunResult(
        "completed", 0, 0, ("data_unchanged",), 0, tmp_path,
    ))

    assert any("이번 학습" in line and "모의운영 후보" in line for line in logs)
    assert not any("전략은 아직 없습니다" in line for line in logs)


def test_learning_feedback_does_not_imply_live_approval(tmp_path: Path) -> None:
    view = DashboardRenderMixin()
    view.status_var = TextValue()
    logs: list[str] = []
    view._append_log = logs.append

    view._render_learning_result(LearningRunResult(
        "completed", 1, 1, (), 0, tmp_path,
    ))

    assert any("모의운영 후보" in line and "등록" in line for line in logs)
    assert any("실거래" in line and "별도" in line for line in logs)


def test_holdout_rejections_have_actionable_korean_explanations() -> None:
    reasons = (
        "independent_validation_required", "holdout_fixed_rule_unsupported",
        "holdout_cost_assumptions_invalid", "holdout_config_invalid",
        "holdout_history_insufficient", "holdout_backtest_failed",
        "holdout_evidence_invalid", "holdout_closed_trades_insufficient",
        "holdout_return_not_positive", "holdout_risk_adjusted_return_not_positive",
        "holdout_profit_factor_unavailable", "holdout_profit_factor_too_low",
        "holdout_drawdown_too_high", "holdout_turnover_too_high",
    )

    explanations = tuple(human_reason(reason) for reason in reasons)

    assert all("별도" in explanation for explanation in explanations)
    assert len(set(explanations)) == len(reasons)
