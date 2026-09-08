from __future__ import annotations

from .cli_types import JsonObject
from .models import AccountSnapshot
from .quant_data.symbol_selector import SelectionReport
from .broker_response import broker_response_submitted


def _account_to_dict(account: AccountSnapshot) -> JsonObject:
    """Return rounded account values for CLI diagnostics."""

    return {
        "cash": round(account.cash, 4),
        "equity": round(account.equity, 4),
        "buying_power": round(account.buying_power, 4),
    }


def selection_report_to_dict(report: SelectionReport) -> JsonObject:
    return {
        "status": report.status,
        "universe_id": report.universe_id,
        "universe_effective_date": report.universe_effective_date,
        "universe_version": report.universe_version,
        "strategy_id": report.strategy_id,
        "strategy_version": report.strategy_version,
        "strategy_digest": report.strategy_digest,
        "shortlist_count": report.shortlist_count,
        "ranked": [
            {
                "symbol": item.symbol,
                "score": item.score,
                "confidence": item.confidence,
                "reasons": list(item.reasons),
            }
            for item in report.ranked
        ],
        "selected_symbols": list(report.selected_symbols),
        "warnings": list(report.warnings),
        "blocked_reasons": list(report.blocked_reasons),
        "submitted_order": False,
    }


def automatic_cycle_to_dict(report: SelectionReport | None, items: list[dict]) -> JsonObject:
    if report is None:
        return {
            "status": "blocked",
            "reason": "selection_report_unavailable",
            "submitted_order": False,
        }
    execution = []
    for item in items:
        decision = item["decision"]
        response = item.get("response")
        execution.append(
            {
                "symbol": item["symbol"],
                "action": decision.action if decision is not None else None,
                "score": decision.score if decision is not None else None,
                "response_status": response.get("status")
                if isinstance(response, dict)
                else None,
                "response_reason": response.get("reason")
                if isinstance(response, dict)
                else None,
                "terminal": response.get("terminal") is True
                if isinstance(response, dict)
                else False,
                "broker_submitted": (
                    response.get("broker_submitted") is True
                    or broker_response_submitted(response)
                )
                if isinstance(response, dict)
                else False,
            }
        )
    terminal = next((item for item in execution if item["terminal"]), None)
    submitted_order = any(item["broker_submitted"] for item in execution)
    if terminal is not None:
        return {
            "status": "blocked",
            "reason": terminal["response_reason"],
            "selection": selection_report_to_dict(report),
            "execution": execution,
            "submitted_order": submitted_order,
        }
    return {
        "status": report.status,
        "selection": selection_report_to_dict(report),
        "execution": execution,
        "submitted_order": submitted_order,
    }
