from __future__ import annotations

import argparse
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditLogger
from nasdaq_auto_trader.ai_quant_lab.config import load_ai_quant_config
from nasdaq_auto_trader.ai_quant_lab.degradation_monitor import DegradationMonitor
from nasdaq_auto_trader.ai_quant_lab.operator_models import OperatorPaths
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.types import JsonObject


def monitor_degradation_payload(
    args: argparse.Namespace,
    paths: OperatorPaths,
) -> JsonObject:
    config = load_ai_quant_config(paths.ai_config_path)
    audit = AuditLogger(paths.audit_log_path)
    registry = StrategyRegistry(paths.registry_path, paths.promoted_path, config, audit)
    result = DegradationMonitor(config, registry, audit).evaluate(Path(args.ledger_path))
    payload = result.to_json_object()
    payload["command"] = "monitor-degradation"
    return payload
