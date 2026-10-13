from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .ai_quant_lab.config import AIQuantConfig
from .ai_quant_lab.holdout_validation import HOLDOUT_PROTOCOL_VERSION, HoldoutEvidence
from .ai_quant_lab.operator_market_data import BarsBySymbol
from .ai_quant_lab.scoring_engine import StrategyScore
from .ai_quant_lab.storage import safe_artifact_path
from .ai_quant_lab.strategy_schema import StrategySpec
from .ai_quant_lab.validation_engine import ADVANCED_METRIC_NAMES
from .learning_validation import learning_policy


def save_learning_report(
    report_dir: Path,
    spec: StrategySpec,
    bars_by_symbol: BarsBySymbol,
    score: StrategyScore,
    *,
    evidence: HoldoutEvidence | None = None,
    config: AIQuantConfig | None = None,
) -> Path:
    serialized_model = json.dumps(
        spec.raw,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    timestamps = [bar.timestamp for bars in bars_by_symbol.values() for bar in bars]
    payload = {
        "strategy_id": spec.strategy_id,
        "model_version": spec.version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_start": min(timestamps),
        "data_end": max(timestamps),
        "universe": sorted(bars_by_symbol),
        "feature_version": "price-features-v1",
        "code_version": os.environ.get("NASDAQ_AUTO_TRADER_CODE_VERSION", "source-tree"),
        "random_seed": 0,
        "hyperparameters": spec.raw.get("signals", []),
        "validation_metrics": score.metrics,
        "evidence_scope": (
            "fixed_rule_temporal_holdout" if evidence and evidence.backtest
            else "single_backtest_in_sample"
        ),
        "learning_protocol_version": HOLDOUT_PROTOCOL_VERSION if evidence else "in-sample-v1",
        "validation_policy": learning_policy(config) if config else {},
        "holdout_evidence": evidence.to_json_object() if evidence else None,
        "missing_advanced_metrics": list(ADVANCED_METRIC_NAMES),
        "transaction_cost_assumptions": {
            "source": "ai_quant_config",
            "commission_bps": config.commission_bps if config else None,
            "slippage_bps": config.slippage_bps if config else None,
        },
        "model_sha256": hashlib.sha256(serialized_model).hexdigest(),
        "promotion_decision": "rejected" if score.rejection_reasons else "validation_passed",
        "rejection_reasons": list(score.rejection_reasons),
        "promoted_to_live": False,
        "promotion_reason": "live promotion requires paper evidence and manual approval",
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    target = report_dir / f"{spec.strategy_id}-{spec.version}.json"
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def save_strategy_artifact(spec_dir: Path, spec: StrategySpec) -> Path:
    spec_dir.mkdir(parents=True, exist_ok=True)
    target = safe_artifact_path(
        spec_dir,
        f"{spec.strategy_id}-{spec.version}",
        ".json",
    )
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(spec.raw, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target
