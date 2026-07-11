import unittest
from pathlib import Path

from nasdaq_auto_trader.app_ui_actions import DashboardActionsMixin
from nasdaq_auto_trader.app_ui_render import DashboardRenderMixin
from nasdaq_auto_trader.learning_runner import LearningRunResult


class LearningGuiTests(unittest.TestCase):
    def test_learning_button_starts_orderless_learning_task(self):
        app = DashboardActionsMixin()
        labels = []
        logs = []
        app._append_log = logs.append
        app._start_task = lambda label, task: labels.append((label, task)) or True
        app._update_controls = lambda: None

        app._start_learning_only()

        self.assertEqual(labels[0][0], "learn")
        self.assertIn("학습만 실행", logs[0])

    def test_learning_button_does_not_log_when_worker_is_busy(self):
        app = DashboardActionsMixin()
        logs = []
        app._append_log = logs.append
        app._start_task = lambda label, task: False
        app._update_controls = lambda: None

        app._start_learning_only()

        self.assertEqual(logs, [])

    def test_learning_result_logs_reasons_and_zero_orders(self):
        view = DashboardRenderMixin()
        logs = []
        view._append_log = logs.append
        view.status_var = _Variable("")
        result = LearningRunResult(
            status="aborted",
            generated_candidates=0,
            accepted_candidates=0,
            reasons=("insane_search_unavailable",),
            submitted_orders=0,
            artifact_root=Path("C:/Users/test/AppData/Local/NasdaqAutoTrader/ai_quant_lab"),
        )

        view._render_learning_result(result)

        rendered = "\n".join(logs)
        self.assertEqual(view.status_var.get(), "학습 중단")
        self.assertIn("상태: 중단", rendered)
        self.assertIn("제출된 실제 주문: 0건", rendered)
        self.assertIn("리서치 명령이 없어 연구 루프를 실행할 수 없음", rendered)
        self.assertNotIn("aborted", rendered)
        self.assertNotIn("insane_search_unavailable", rendered)


class _Variable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


if __name__ == "__main__":
    unittest.main()
