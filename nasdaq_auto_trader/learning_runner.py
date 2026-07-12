from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import default_strategy_artifact_paths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditLogger
from nasdaq_auto_trader.ai_quant_lab.backtest_engine import BacktestEngine, BacktestRequest
from nasdaq_auto_trader.ai_quant_lab.backtest_market_data import validate_backtest_market_data
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig, load_ai_quant_config
from nasdaq_auto_trader.ai_quant_lab.operator_market_data import BarsBySymbol
from nasdaq_auto_trader.ai_quant_lab.operator_models import OperatorPaths
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.registry_models import StrategyStatus
from nasdaq_auto_trader.ai_quant_lab.scoring_engine import ScoringEngine
from nasdaq_auto_trader.ai_quant_lab.strategy_schema_validation import parse_strategy_spec_json
from nasdaq_auto_trader.ai_quant_lab.validation_engine import ValidationEngine
from nasdaq_auto_trader.file_lock import FileLockTimeout, exclusive_file_lock
from nasdaq_auto_trader.learning_strategy_template import candidate_payload
from nasdaq_auto_trader.learning_report import (
    save_learning_report,
    save_strategy_artifact,
)


@dataclass(frozen=True, slots=True)
class LearningProgress:
    stage: str
    percent: int
    detail: str


class LearningCancellation:
    def __init__(self, reporter: Callable[[LearningProgress], None] | None = None) -> None:
        self._event = threading.Event()
        self._reporter = reporter

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def report(self, stage: str, percent: int, detail: str = "") -> None:
        if self._reporter is not None:
            self._reporter(LearningProgress(stage, percent, detail))


@dataclass(frozen=True, slots=True)
class LearningRunResult:
    status: str
    generated_candidates: int
    accepted_candidates: int
    reasons: tuple[str, ...]
    submitted_orders: int
    artifact_root: Path


def run_learning_only(
    paths: OperatorPaths | None = None,
    bars_by_symbol: BarsBySymbol | None = None,
    cancellation: LearningCancellation | None = None,
) -> LearningRunResult:
    runtime_paths = paths or _default_operator_paths()
    control = cancellation or LearningCancellation()
    if control.cancelled:
        return _result(runtime_paths, "cancelled", 0, ("learning_cancelled",))
    try:
        with exclusive_file_lock(runtime_paths.spec_dir.parent / "learning.lock", 0.0):
            return _run_locked(runtime_paths, bars_by_symbol or {}, control)
    except FileLockTimeout:
        return _result(runtime_paths, "blocked", 0, ("learning_already_running",))


def _run_locked(
    paths: OperatorPaths,
    bars_by_symbol: BarsBySymbol,
    control: LearningCancellation,
) -> LearningRunResult:
    control.report("data_validation", 10, _data_range(bars_by_symbol))
    _, market_data_reason = validate_backtest_market_data(bars_by_symbol, 100_000.0)
    if market_data_reason:
        return _result(paths, "blocked", 0, (market_data_reason,))
    if control.cancelled:
        return _result(paths, "cancelled", 0, ("learning_cancelled",))

    config = _ensure_learning_config(paths.ai_config_path)
    audit = AuditLogger(paths.audit_log_path)
    validation = parse_strategy_spec_json(
        json.dumps(candidate_payload(bars_by_symbol), ensure_ascii=False)
    )
    if not validation.valid or validation.spec is None:
        return _result(paths, "failed", 0, validation.reasons)
    report_path = (
        paths.spec_dir
        / "reports"
        / f"{validation.spec.strategy_id}-{validation.spec.version}.json"
    )
    registry = StrategyRegistry(paths.registry_path, paths.promoted_path, config, audit)
    artifact_path = paths.spec_dir / f"{validation.spec.strategy_id}-{validation.spec.version}.json"
    completed_record = next(
        (
            record
            for record in registry.load_records()
            if record.strategy_id == validation.spec.strategy_id
            and record.version == validation.spec.version
            and record.status is StrategyStatus.PAPER_CANDIDATE
        ),
        None,
    )
    if report_path.exists() and artifact_path.exists() and completed_record is not None:
        return _result(paths, "completed", 0, ("data_unchanged",))

    control.report("backtest", 45, validation.spec.strategy_id)
    backtest = BacktestEngine(config, audit).run(
        BacktestRequest(validation.spec, bars_by_symbol)
    )
    if control.cancelled:
        return _result(paths, "cancelled", 0, ("learning_cancelled",))
    control.report("walk_forward_validation", 70, validation.spec.version)
    verified = ValidationEngine(audit).validate(backtest)
    score = ScoringEngine(audit).score(backtest, verified)
    reasons = tuple(
        dict.fromkeys(
            (*backtest.rejection_reasons, *verified.rejection_reasons, *score.rejection_reasons)
        )
    )
    if not backtest.success or not verified.promotion_eligible or reasons:
        control.report("champion_comparison", 100, "champion_retained")
        return _result(paths, "completed", 0, reasons)
    if control.cancelled:
        return _result(paths, "cancelled", 0, ("learning_cancelled",))

    save_strategy_artifact(paths.spec_dir, validation.spec)
    promotion = registry.evaluate_promotion(
        validation.spec,
        score,
        requested_status=StrategyStatus.PAPER_CANDIDATE,
    )
    if not promotion.allowed:
        return _result(paths, "completed", 0, promotion.reasons)
    save_learning_report(paths.spec_dir / "reports", validation.spec, bars_by_symbol, score)
    control.report("completed", 100, "validation_passed")
    return _result(paths, "completed", 1, ())


def _ensure_learning_config(path: Path | None) -> AIQuantConfig:
    if path is None:
        return AIQuantConfig()
    existing = load_ai_quant_config(path)
    safe_config = replace(
        existing,
        ai_quant_lab_enabled=True,
        self_improvement_enabled=True,
        research_provider="insane_search",
        allow_only_insane_search_for_research=True,
        disable_research_if_insane_search_unavailable=True,
        live_trading=False,
        dry_run=True,
        allow_ai_direct_order=False,
        allow_dynamic_code_execution=False,
        max_strategy_candidates_per_run=1,
        max_parallel_backtests=1,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(safe_config.to_json_object(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return safe_config


def _result(
    paths: OperatorPaths,
    status: str,
    accepted: int,
    reasons: tuple[str, ...],
) -> LearningRunResult:
    return LearningRunResult(status, 1 if status == "completed" else 0, accepted, reasons, 0, paths.spec_dir.parent)


def _data_range(bars_by_symbol: BarsBySymbol) -> str:
    timestamps = [bar.timestamp for bars in bars_by_symbol.values() for bar in bars]
    return f"{min(timestamps)} ~ {max(timestamps)}" if timestamps else ""


def _default_operator_paths() -> OperatorPaths:
    defaults = default_strategy_artifact_paths()
    return OperatorPaths(
        defaults.ai_config_path,
        defaults.registry_path,
        defaults.promoted_path,
        defaults.spec_dir,
        defaults.audit_log_path,
    )
