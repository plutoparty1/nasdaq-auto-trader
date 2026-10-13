from __future__ import annotations

import threading
import time
import tkinter as tk
from collections.abc import Callable, Iterator

import pytest

from nasdaq_auto_trader import p1_ops_gui
from nasdaq_auto_trader.p1_ops_gui_contract import CONFIRMATION, LiveReview, OpsStatus, Position
from nasdaq_auto_trader.p1_ops_gui_review import LiveRequest


class BrokerFailure(RuntimeError):
    pass


class FakeController:
    def __init__(self) -> None:
        self.mode = "local_paper"
        self.running = False
        self.entries_paused = False
        self.closed = False
        self.fail_start = False
        self.calls: list[tuple[str, str]] = []
        self.thread_ids: set[int] = set()
        self.requests: list[LiveRequest] = []
        self.positions: list[Position] = []
        self.release_step = threading.Event()
        self.release_step.set()
        self.step_entered = threading.Event()

    def _call(self, name: str) -> None:
        self.thread_ids.add(threading.get_ident())
        self.calls.append((name, self.mode))

    def start(self, mode: str) -> None:
        self.mode = mode
        self._call("start")
        if self.fail_start or mode == "live":
            raise BrokerFailure("account 1234567890 must never enter GUI logs")
        self.running = True

    def pause_entries(self) -> None:
        self._call("pause")
        self.entries_paused = True

    def resume_entries(self) -> None:
        self._call("resume")
        self.entries_paused = False

    def step(self) -> None:
        self._call("step")
        self.step_entered.set()
        self.release_step.wait(timeout=5)

    def status(self) -> OpsStatus:
        self._call("status")
        return {
            "mode": self.mode, "running": self.running,
            "entries_paused": self.entries_paused, "message": "조건 대기",
            "updated_at": "2026-10-12T10:00:00Z", "cash": 1000.0,
            "equity": 1100.0, "positions": self.positions, "pending": [],
            "version": "P1-test", "blockers": ["실전 운영 및 수익성 미검증"],
        }

    def live_review(self) -> LiveReview:
        self._call("review")
        return {"account": "******78", "version": "P1-test",
                "required_action": "전용 KIS 모의 인증과 실제 비용을 확인하세요."}

    def record_live_request(self, account: str, allocation_usd: float, loss_stop_pct: float, confirm: str) -> None:
        self._call("request")
        self.requests.append(LiveRequest(account, allocation_usd, loss_stop_pct, confirm))

    def close(self) -> None:
        self._call("close")
        self.running = False
        self.closed = True


def pump_until(root: tk.Tk, condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        root.update()
        assert time.monotonic() < deadline, "Tk operation failed to complete"
        threading.Event().wait(0.005)


@pytest.fixture
def gui() -> Iterator[tuple[tk.Tk, FakeController, p1_ops_gui.P1OpsApp]]:
    root = tk.Tk()
    root.withdraw()
    controller = FakeController()
    app = p1_ops_gui.P1OpsApp(root, controller)
    pump_until(root, lambda: not app.busy)
    yield root, controller, app
    controller.release_step.set()
    if not app.closed:
        app.close()
        pump_until(root, lambda: app.closed)


def test_default_window_is_stopped_local_and_reuses_dashboard(gui) -> None:
    root, controller, app = gui
    assert not controller.running
    assert app.selected_mode.get() == "local_paper"
    assert "LOCAL" in app.mode_var.get()
    assert app.positions_tree.winfo_exists()
    assert root.protocol("WM_DELETE_WINDOW")


def test_buttons_call_controller_on_one_background_worker(gui) -> None:
    root, controller, app = gui
    for button in (app.start_button, app.pause_button, app.resume_button, app.refresh_button):
        button.invoke()
        pump_until(root, lambda: not app.busy)
    assert [name for name, _ in controller.calls if name != "status"] == [
        "start", "pause", "resume", "step",
    ]
    assert controller.thread_ids != {threading.get_ident()}
    assert len(controller.thread_ids) == 1


@pytest.mark.parametrize("mode,label", [("kis_paper", "KIS"), ("live", "LIVE")])
def test_mode_selection_is_distinct_and_never_autostarts(gui, mode, label) -> None:
    root, controller, app = gui
    app.selected_mode.set(mode)
    app.mode_combo.event_generate("<<ComboboxSelected>>")
    root.update()
    assert label in app.mode_var.get()
    assert "현재 표시: LOCAL" in app.mode_var.get()
    assert not controller.running
    assert not any(name == "start" for name, _ in controller.calls)


def test_failed_start_remains_stopped_and_redacts_error(gui) -> None:
    root, controller, app = gui
    controller.fail_start = True
    app.start_button.invoke()
    pump_until(root, lambda: not app.busy)
    assert not controller.running
    assert not app.start_button.instate(["disabled"])
    assert "오류" in app.status_var.get()
    assert "1234567890" not in app.log_text.get("1.0", "end")


def test_close_waits_for_active_worker_and_leaves_no_worker(gui) -> None:
    root, controller, app = gui
    controller.release_step.clear()
    app.refresh_button.invoke()
    assert controller.step_entered.wait(timeout=2)
    app.close()
    root.update()
    assert not app.closed
    assert not controller.closed
    controller.release_step.set()
    pump_until(root, lambda: app.closed)
    assert controller.closed
    assert controller.calls[-1][0] == "close"
    assert not any(thread.name.startswith("p1-ops-gui") for thread in threading.enumerate())


def test_live_request_dialog_records_explicit_request_without_start(gui) -> None:
    root, controller, app = gui
    app.learning_button.invoke()
    pump_until(root, lambda: not app.busy)
    dialog = app._review_dialog
    assert dialog is not None
    dialog.account.set("12345678")
    dialog.allocation.set("250")
    dialog.loss_stop.set("5")
    dialog.confirm.set(CONFIRMATION)
    dialog.save_button.invoke()
    pump_until(root, lambda: not app.busy)
    assert controller.requests == [LiveRequest("12345678", 250, .05, CONFIRMATION)]
    assert not controller.running
    assert not any(name == "start" for name, _ in controller.calls)
    assert "12345678" not in app.log_text.get("1.0", "end")


def test_live_review_displays_required_action_from_controller(gui) -> None:
    root, controller, app = gui
    app.learning_button.invoke()
    pump_until(root, lambda: not app.busy)
    dialog = app._review_dialog
    assert dialog is not None
    assert "전용 KIS 모의 인증과 실제 비용을 확인하세요." in [
        label.cget("text") for label in dialog.value_labels
    ]


def test_paused_entries_continue_protection_steps(gui) -> None:
    root, controller, app = gui
    app.start_button.invoke()
    pump_until(root, lambda: not app.busy)
    app.pause_button.invoke()
    pump_until(root, lambda: not app.busy)
    root.after_cancel(app._tick_id)
    app._tick()
    pump_until(root, lambda: not app.busy)
    assert controller.running and controller.entries_paused
    assert ("step", "local_paper") in controller.calls


def test_holdings_render_unknown_high_water_and_real_market_value(gui) -> None:
    root, controller, app = gui
    controller.positions = [{
        "symbol": "CMCSA", "qty": 2, "avg_entry_price": 30,
        "market_value": 64, "high_water_price": None,
    }]
    app.refresh_button.invoke()
    pump_until(root, lambda: not app.busy)
    rows = app.positions_tree.get_children()
    assert len(rows) == 1
    values = app.positions_tree.item(rows[0], "values")
    assert values[0] == "CMCSA" and values[3] == "-"
    assert values[4] == "64.00" and values[5] == "+4.00"
