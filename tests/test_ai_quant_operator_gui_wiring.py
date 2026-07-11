import unittest
from unittest.mock import patch

from nasdaq_auto_trader.ai_quant_lab import operator_gui
from nasdaq_auto_trader.ai_quant_lab.operator_gui import AIQuantOperatorApp
from nasdaq_auto_trader.ai_quant_lab.operator_gui_models import OperatorGuiResult


class AIQuantOperatorGuiWiringTests(unittest.TestCase):
    def test_state_changing_actions_do_not_run_when_confirmation_is_cancelled(self):
        app = _app_with(_FakeController(), confirm=False)

        app._run_nightly()
        app._run_champion_lock()
        app._run_paper_shadow()
        app._run_rollback()

        self.assertEqual(app.controller.calls, [])

    def test_nightly_uses_configured_research_command_only_after_confirmation(self):
        controller = _FakeController()
        app = _app_with(controller, confirm=True)

        app._run_nightly()

        self.assertEqual(controller.calls, ["nightly"])
        self.assertEqual(controller.nightly_command, ())

    def test_paper_shadow_runs_only_after_confirmation(self):
        controller = _FakeController()
        app = _app_with(controller, confirm=True)

        app._run_paper_shadow()

        self.assertEqual(controller.calls, ["paper-shadow"])

    def test_live_guard_button_maps_to_status_check_not_live_cycle(self):
        controller = _FakeController()
        app = _app_with(controller, confirm=True)
        live_guard = app._action_command("live-guard")

        with patch.object(
            operator_gui.messagebox,
            "showinfo",
            side_effect=AssertionError("live guard must not open a modal dialog"),
        ):
            live_guard()

        self.assertEqual(controller.calls, ["status"])


def _app_with(controller, confirm: bool):
    app = AIQuantOperatorApp.__new__(AIQuantOperatorApp)
    app.controller = controller
    app.candidate_var = _Value("")
    app.strategy_id_var = _Value("strategy-1")
    app.strategy_version_var = _Value("v1")
    app.symbol_var = _Value("QQQ")
    app.side_var = _Value("buy")
    app.price_var = _Value("100")
    app.mode_var = _Value("paper")
    app.ledger_var = _Value("")
    app.rollback_reason_var = _Value("operator_manual_no_trade_rollback")
    app._confirm = lambda title, message: confirm
    app._run_action = lambda action: action()
    return app


class _Value:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class _FakeController:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.nightly_command: tuple[str, ...] | None = None

    def status(self) -> OperatorGuiResult:
        self.calls.append("status")
        return OperatorGuiResult("status", {"command": "status"}, 0, "status")

    def nightly(
        self,
        insane_search_command: tuple[str, ...],
        candidate_json,
    ) -> OperatorGuiResult:
        self.calls.append("nightly")
        self.nightly_command = insane_search_command
        return OperatorGuiResult("nightly", {"command": "nightly", "status": "completed"}, 0, "nightly")

    def champion_lock(self, strategy_id: str, strategy_version: str) -> OperatorGuiResult:
        self.calls.append("champion-lock")
        return OperatorGuiResult("champion-lock", {"command": "champion-lock"}, 0, "champion-lock")

    def rollback(self, reason: str) -> OperatorGuiResult:
        self.calls.append("rollback")
        return OperatorGuiResult("rollback", {"command": "rollback"}, 0, "rollback")

    def paper_shadow(
        self,
        ledger_path,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        side: str,
        price: float,
        mode: str,
        equity: float,
        cash: float,
    ) -> OperatorGuiResult:
        self.calls.append("paper-shadow")
        return OperatorGuiResult(
            "paper-shadow",
            {"command": "paper-shadow", "submitted_orders": 0},
            0,
            "paper-shadow",
        )


if __name__ == "__main__":
    unittest.main()
