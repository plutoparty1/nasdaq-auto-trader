"""Explicit user draft editing; never grants an authorization."""
from __future__ import annotations

import json
import math
from pathlib import Path

from .ai_quant_lab.types import JsonObject, JsonValue
from .production_checks import conflicting_processes
from .production_runtime import ProductionRuntime


def _read(path: Path) -> JsonObject:
    value: JsonValue = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError("draft_object_required")
    return value


def update_draft(runtime: ProductionRuntime, changes: dict[str, float]) -> JsonObject:
    conflicts = conflicting_processes(runtime)
    if conflicts:
        return {"status": "blocked", "reason": "close_trader_before_draft_edit", "conflicts": list[JsonValue](conflicts)}
    for name, value in changes.items():
        maximum = 100 if name.endswith("pct") else 1_000_000
        if not math.isfinite(value) or not 0 < value <= maximum:
            raise ValueError("invalid_draft_limit:" + name)
    config_path = runtime.app_dir / "config.operating.json"
    settings_path = runtime.app_dir / "trading_config.json"
    ai_path = runtime.paths.root / "ai_quant_config.json"
    config, settings, ai = _read(config_path), _read(settings_path), _read(ai_path)
    risk = config.get("risk")
    if not isinstance(risk, dict):
        raise TypeError("draft_risk_object_required")
    for name, value in changes.items():
        fraction = value / 100
        match name:
            case "single_position_pct":
                risk["max_position_pct"] = fraction
                ai["max_single_position_pct"] = fraction
            case "total_exposure_pct":
                ai["max_total_exposure_pct"] = fraction
            case "max_order_usd":
                risk["max_order_notional"] = value
                ai["max_order_notional"] = value
            case "risk_per_trade_pct":
                risk["risk_per_trade_pct"] = fraction
            case "stop_loss_pct":
                settings["stop_loss_rate"] = value
            case "daily_loss_pct":
                settings["max_daily_loss_rate"] = value
                ai["max_daily_loss_pct"] = fraction
            case "roundtrip_cost_pct":
                risk["estimated_roundtrip_cost_pct"] = fraction
            case _:
                raise ValueError("unknown_draft_limit:" + name)
    if not changes:
        return {"status": "draft_unchanged", "approval_issued": False}
    for path, data in ((config_path, config), (settings_path, settings), (ai_path, ai)):
        _ = path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _ = (runtime.app_dir / "fee-review.json").write_text(json.dumps({"confirmed": False,
        "source": "draft_limits_changed_requires_user_fee_review"}), encoding="utf-8")
    return {"status": "draft_changed", "changes": {key: value for key, value in changes.items()}, "fixed_qty": 1,
            "approval_issued": False, "requires_fresh_preflight_and_explicit_approval": True}
