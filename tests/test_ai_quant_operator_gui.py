import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.operator_cli import main
from nasdaq_auto_trader.ai_quant_lab.operator_gui_controller import AIQuantGuiController
from nasdaq_auto_trader.ai_quant_lab.operator_gui_models import OperatorGuiInputError
from nasdaq_auto_trader.ai_quant_lab.operator_gui_presenter import (
    gui_result_explanation,
    gui_status_view,
    human_reason,
    operator_action_cards,
)
from nasdaq_auto_trader.ai_quant_lab.operator_models import OperatorPaths
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject
from tests.ai_quant_fixtures import promoted_payload


class AIQuantOperatorGuiTests(unittest.TestCase):
    def test_status_action_reports_fail_closed_live_guard(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = AIQuantGuiController(_operator_paths(Path(temp_dir)))
            result = controller.status()

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.payload["command"], "status")
        self.assertEqual(result.payload["live_block_reason"], "live_trading_disabled")
        self.assertIn("live_trading_disabled", result.summary)

    def test_nightly_action_aborts_without_insane_search_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "ai_quant_config.json"
            config_path.write_text(
                json.dumps(
                    AIQuantConfig(
                        ai_quant_lab_enabled=True,
                        self_improvement_enabled=True,
                    ).to_json_object()
                ),
                encoding="utf-8",
            )
            controller = AIQuantGuiController(_operator_paths(root, config_path))
            result = controller.nightly(insane_search_command=(), candidate_json=None)

        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.payload["status"], "aborted")
        self.assertIn("insane_search_unavailable", result.payload["reasons"])

    def test_paper_shadow_action_writes_ledger_without_submitting_orders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger_path = Path(temp_dir) / "paper.jsonl"
            controller = AIQuantGuiController(_operator_paths(Path(temp_dir)))
            result = controller.paper_shadow(
                ledger_path=ledger_path,
                strategy_id="strategy-1",
                strategy_version="v1",
                symbol="QQQ",
                side="buy",
                price=100.0,
                mode="paper",
                equity=100_000.0,
                cash=100_000.0,
            )
            ledger_lines = ledger_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.payload["status"], "completed")
        self.assertEqual(result.payload["submitted_orders"], 0)
        self.assertEqual(len(ledger_lines), 1)

    def test_paper_shadow_action_rejects_blank_symbol(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = AIQuantGuiController(_operator_paths(Path(temp_dir)))
            with self.assertRaisesRegex(OperatorGuiInputError, "symbol is required"):
                controller.paper_shadow(
                    ledger_path=None,
                    strategy_id="strategy-1",
                    strategy_version="v1",
                    symbol=" ",
                    side="buy",
                    price=100.0,
                    mode="paper",
                    equity=100_000.0,
                    cash=100_000.0,
                )

    def test_gui_controller_does_not_expose_live_cycle(self):
        self.assertFalse(hasattr(AIQuantGuiController, "live_cycle"))

    def test_rollback_action_requires_plain_reason(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = AIQuantGuiController(_operator_paths(Path(temp_dir)))
            with self.assertRaisesRegex(OperatorGuiInputError, "rollback reason is required"):
                controller.rollback(" ")

    def test_rollback_action_rewrites_promoted_strategy_to_no_trade(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            promoted_path = root / "promoted.json"
            promoted_path.write_text(json.dumps(promoted_payload("s1")), encoding="utf-8")
            controller = AIQuantGuiController(_operator_paths(root))
            result = controller.rollback("operator_manual_no_trade_rollback")
            promoted = json.loads(promoted_path.read_text(encoding="utf-8"))

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.payload["status"], "completed")
        self.assertEqual(promoted["status"], "rollback")
        self.assertFalse(promoted["allowed_for_live"])
        self.assertEqual(promoted["mode"], "no_trade")

    def test_status_view_uses_plain_safety_language(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = AIQuantGuiController(_operator_paths(Path(temp_dir)))
            result = controller.status()
            view = gui_status_view(result)

        self.assertEqual(view.badge_text, "실주문 차단")
        self.assertEqual(view.badge_level, "safe")
        self.assertIn("실제 주문이 나가지 않습니다", view.headline)
        self.assertIn("GUI 실주문 버튼: 없음", view.checklist)

    def test_result_explanation_puts_plain_text_before_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = AIQuantGuiController(_operator_paths(Path(temp_dir)))
            result = controller.paper_shadow(
                ledger_path=None,
                strategy_id="strategy-1",
                strategy_version="v1",
                symbol="QQQ",
                side="buy",
                price=100.0,
                mode="paper",
                equity=100_000.0,
                cash=100_000.0,
            )

        explanation = "\n".join(gui_result_explanation(result))
        self.assertIn("작업: 페이퍼/섀도우 리허설", explanation)
        self.assertIn("제출된 실제 주문: 0건", explanation)
        self.assertIn("가상 체결: 1건", explanation)

    def test_reason_labels_do_not_expose_raw_internal_codes(self):
        self.assertEqual(
            human_reason("turnover_too_high"),
            "거래 회전율이 너무 높음",
        )
        self.assertEqual(
            human_reason("unknown_internal_reason"),
            "한글 설명이 등록되지 않은 내부 점검 사유입니다.",
        )

    def test_operator_cards_do_not_expose_live_order_execution(self):
        cards = operator_action_cards()
        labels = "\n".join(card.title + "\n" + card.safety_note for card in cards)

        self.assertIn("실거래 차단 점검", labels)
        self.assertIn("이 GUI는 실제 주문 실행 버튼을 제공하지 않습니다.", labels)
        self.assertNotIn("실거래 실행", labels)
        self.assertNotIn("라이브 시작", labels)

    def test_gui_smoke_cli_checks_controller_without_opening_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        "--registry-path",
                        str(Path(temp_dir) / "registry.json"),
                        "--promoted-path",
                        str(Path(temp_dir) / "promoted.json"),
                        "gui",
                        "--smoke",
                    ]
                )

        payload = _json_payload(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["command"], "gui")
        self.assertEqual(payload["surface"], "desktop")
        self.assertEqual(payload["live_block_reason"], "live_trading_disabled")
        self.assertTrue(payload["safe_operator_console"])
        self.assertEqual(payload["live_order_surface"], "not_exposed")
        self.assertIn("rollback", payload["operator_actions"])


def _operator_paths(root: Path, config_path: Path | None = None) -> OperatorPaths:
    return OperatorPaths(
        config_path,
        root / "registry.json",
        root / "promoted.json",
        root / "specs",
        root / "audit.jsonl",
    )


def _json_payload(value: str) -> JsonObject:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise AssertionError(payload)
    return payload


if __name__ == "__main__":
    unittest.main()
