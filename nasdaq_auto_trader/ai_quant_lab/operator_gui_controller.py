from __future__ import annotations

import argparse
import json
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.operator_gui_models import (
    OperatorGuiInputError,
    OperatorGuiResult,
)
from nasdaq_auto_trader.ai_quant_lab.operator_gui_presenter import operator_action_cards
from nasdaq_auto_trader.ai_quant_lab.operator_models import (
    OperatorCommand,
    OperatorPaths,
    TradeSide,
    UnsupportedCommandError,
)
from nasdaq_auto_trader.ai_quant_lab.operator_runtime import (
    exit_code,
    run_operator_command,
)
from nasdaq_auto_trader.ai_quant_lab.paper_shadow import PaperShadowMode
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject, JsonValue


class AIQuantGuiController:
    def __init__(self, paths: OperatorPaths) -> None:
        self.paths = paths

    def status(self) -> OperatorGuiResult:
        return self._run("status", argparse.Namespace())

    def nightly(
        self,
        insane_search_command: tuple[str, ...],
        candidate_json: Path | None,
        bars_json: Path | None = None,
    ) -> OperatorGuiResult:
        return self._run(
            "nightly",
            argparse.Namespace(
                insane_search_command=insane_search_command,
                candidate_json=str(candidate_json) if candidate_json else None,
                bars_json=str(bars_json) if bars_json else None,
            ),
        )

    def champion_lock(
        self,
        strategy_id: str,
        strategy_version: str,
    ) -> OperatorGuiResult:
        return self._run(
            "champion-lock",
            argparse.Namespace(
                strategy_id=_required_text(strategy_id, "strategy_id"),
                strategy_version=_required_text(strategy_version, "strategy_version"),
            ),
        )

    def rollback(self, reason: str) -> OperatorGuiResult:
        return self._run(
            "rollback",
            argparse.Namespace(reason=_required_text(reason, "rollback reason")),
        )

    def paper_shadow(
        self,
        ledger_path: Path | None,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        side: TradeSide,
        price: float,
        mode: PaperShadowMode,
        equity: float,
        cash: float,
    ) -> OperatorGuiResult:
        return self._run(
            "paper-shadow",
            argparse.Namespace(
                ledger_path=str(ledger_path) if ledger_path else None,
                strategy_id=_required_text(strategy_id, "strategy_id"),
                strategy_version=_required_text(strategy_version, "strategy_version"),
                symbol=_required_text(symbol, "symbol").upper(),
                side=side,
                price=_positive_number(price, "price"),
                mode=mode,
                equity=_positive_number(equity, "equity"),
                cash=_positive_number(cash, "cash"),
            ),
        )

    def desktop_smoke_payload(self) -> JsonObject:
        payload = self.status().payload.copy()
        payload["command"] = "gui"
        payload["surface"] = "desktop"
        payload["status_command"] = "status"
        payload["safe_operator_console"] = True
        payload["live_order_surface"] = "not_exposed"
        payload["operator_actions"] = [item.key for item in operator_action_cards()]
        return payload

    def _run(self, action: OperatorCommand, args: argparse.Namespace) -> OperatorGuiResult:
        payload = run_operator_command(action, args, self.paths)
        return OperatorGuiResult(
            action=action,
            payload=payload,
            exit_code=exit_code(action, payload),
            summary=summarize_payload(payload),
        )


def parse_trade_side(value: str) -> TradeSide:
    text = value.strip().lower()
    if text == "buy":
        return "buy"
    if text == "sell":
        return "sell"
    raise UnsupportedCommandError(text)


def parse_paper_mode(value: str) -> PaperShadowMode:
    text = value.strip().lower()
    if text == "paper":
        return "paper"
    if text == "shadow":
        return "shadow"
    raise UnsupportedCommandError(text)


def summarize_payload(payload: JsonObject) -> str:
    parts: list[str] = []
    for key in (
        "command",
        "status",
        "live_block_reason",
        "promoted_status",
        "target_status",
        "reasons",
        "blocked_reasons",
        "fills",
        "submitted_orders",
    ):
        value = payload.get(key)
        if _has_summary_value(value):
            parts.append(f"{key}={_format_json_value(value)}")
    return " | ".join(parts)


def pretty_payload(payload: JsonObject) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _required_text(value: str, label: str) -> str:
    text = value.strip()
    if not text:
        raise OperatorGuiInputError(f"{label} is required")
    return text


def _positive_number(value: float, label: str) -> float:
    if value <= 0:
        raise OperatorGuiInputError(f"{label} must be greater than zero")
    return value


def _has_summary_value(value: JsonValue | None) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _format_json_value(value: JsonValue | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return ", ".join(_format_json_value(item) for item in value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
