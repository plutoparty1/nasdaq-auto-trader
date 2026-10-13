from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from .ai_quant_lab.config import AIQuantConfig
from .ai_quant_lab.holdout_validation import HOLDOUT_PROTOCOL_VERSION, HoldoutEvidence
from .ai_quant_lab.strategy_schema import StrategySpec
from .ai_quant_lab.types import JsonObject, JsonValue
from .ai_quant_lab.validation_engine import ValidationResult


def learning_policy(config: AIQuantConfig) -> JsonObject:
    return {
        "protocol_version": HOLDOUT_PROTOCOL_VERSION,
        "min_oos_months": config.min_oos_months,
        "max_strategy_drawdown_pct": config.max_strategy_drawdown_pct,
        "commission_bps": config.commission_bps,
        "slippage_bps": config.slippage_bps,
    }


def report_matches_policy(path: Path, config: AIQuantConfig, spec: StrategySpec) -> bool:
    try:
        payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
        saved: JsonValue = json.loads(
            (path.parent.parent / f"{spec.strategy_id}-{spec.version}.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or not isinstance(saved, dict):
        return False
    holdout = payload.get("holdout_evidence")
    if not isinstance(holdout, dict) or holdout.get("protocol_version") != HOLDOUT_PROTOCOL_VERSION:
        return False
    encoded = json.dumps(saved, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return (
        payload.get("validation_policy") == learning_policy(config)
        and payload.get("learning_protocol_version") == HOLDOUT_PROTOCOL_VERSION
        and payload.get("strategy_id") == spec.strategy_id
        and payload.get("model_version") == spec.version
        and payload.get("model_sha256") == hashlib.sha256(encoded).hexdigest()
        and {key: value for key, value in saved.items() if key != "metadata"}
        == {key: value for key, value in spec.raw.items() if key != "metadata"}
    )


def apply_holdout_screen(basic: ValidationResult, evidence: HoldoutEvidence) -> ValidationResult:
    """A measured temporal screen can qualify paper research, never advanced promotion."""
    eligible = basic.passed and evidence.passed and evidence.backtest is not None
    reasons = tuple(reason for reason in basic.rejection_reasons
                    if not (eligible and reason == "independent_validation_required"))
    return replace(
        basic, paper_eligible=eligible,
        evidence_scope="fixed_rule_temporal_holdout" if evidence.backtest else basic.evidence_scope,
        rejection_reasons=tuple(dict.fromkeys((*reasons, *evidence.reasons))),
    )


def holdout_diagnostics(evidence: HoldoutEvidence) -> tuple[str, ...]:
    if "holdout_history_insufficient" in evidence.reasons:
        return ((f"별도 기간 검증: 공통 일봉 {evidence.metrics['available_bars']:.0f}개 / "
                 f"필요 {evidence.metrics['required_bars']:.0f}개"),)
    if evidence.backtest is None:
        return ()
    return (
        (f"별도 기간 검증: {evidence.test_start[:10]} ~ {evidence.test_end[:10]}, "
        f"평가 {evidence.test_bars}개, 준비 {evidence.warmup_bars}개, "
        f"분리 구간 {evidence.embargo_bars}개"),
        (f"검증 성과: 수익률 {evidence.metrics['total_return']:.2%}, "
        f"최대 낙폭 {evidence.metrics['max_drawdown']:.2%}, "
        f"완료된 가상 거래 {evidence.metrics['trade_count']:.0f}건"),
    )
