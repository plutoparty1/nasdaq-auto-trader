from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

from nasdaq_auto_trader.ai_quant_lab.artifact_paths import default_strategy_artifact_paths
from nasdaq_auto_trader.ai_quant_lab.audit_logger import AuditLogger
from nasdaq_auto_trader.ai_quant_lab.backtest_engine import BacktestEngine, BacktestRequest
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig, load_ai_quant_config
from nasdaq_auto_trader.ai_quant_lab.insane_search_research import (
    InsaneSearchResearchService,
    ResearchContext,
    ResearchResult,
    SourceMetadata,
)
from nasdaq_auto_trader.ai_quant_lab.operator_market_data import BarsBySymbol
from nasdaq_auto_trader.ai_quant_lab.operator_models import OperatorPaths
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.scoring_engine import ScoringEngine
from nasdaq_auto_trader.ai_quant_lab.strategy_factory import AIStrategyFactory
from nasdaq_auto_trader.ai_quant_lab.types import JsonValue
from nasdaq_auto_trader.ai_quant_lab.validation_engine import ValidationEngine
from nasdaq_auto_trader.quant_data.features import PriceBar


@dataclass(frozen=True, slots=True)
class LearningRunResult:
    status: str
    generated_candidates: int
    accepted_candidates: int
    reasons: tuple[str, ...]
    submitted_orders: int
    artifact_root: Path


def run_learning_only(paths: OperatorPaths | None = None) -> LearningRunResult:
    runtime_paths = paths or _default_operator_paths()
    config = _ensure_learning_config(runtime_paths.ai_config_path)
    audit = AuditLogger(runtime_paths.audit_log_path)
    research_service = InsaneSearchResearchService(
        config,
        _LocalBootstrapResearchRunner(),
        audit,
        runtime_paths.spec_dir / "research",
    )
    factory = AIStrategyFactory(
        _LocalBootstrapSpecProvider(),
        audit,
        runtime_paths.spec_dir,
    )
    registry = StrategyRegistry(
        runtime_paths.registry_path,
        runtime_paths.promoted_path,
        config,
        audit,
    )
    context = research_service.build_research_context_for_strategy_generation()
    factory_result = factory.generate_candidates(context, config.max_strategy_candidates_per_run)
    accepted = 0
    reasons = list(factory_result.rejected_reasons)
    for spec in factory_result.accepted:
        registry.register_schema_validated(spec)
        backtest = BacktestEngine(config, audit).run(BacktestRequest(spec, _local_bars_by_symbol()))
        validation = ValidationEngine(audit).validate(backtest)
        score = ScoringEngine(audit).score(backtest, validation)
        if backtest.success and validation.promotion_eligible and not score.rejection_reasons:
            registry.record_validation_passed(spec, score)
            accepted += 1
        else:
            reasons.extend(backtest.rejection_reasons)
            reasons.extend(validation.rejection_reasons)
            reasons.extend(score.rejection_reasons)
    return LearningRunResult(
        status="completed",
        generated_candidates=len(factory_result.accepted) + len(factory_result.rejected_reasons),
        accepted_candidates=accepted,
        reasons=tuple(dict.fromkeys(reasons)),
        submitted_orders=0,
        artifact_root=runtime_paths.spec_dir.parent,
    )


def _default_operator_paths() -> OperatorPaths:
    defaults = default_strategy_artifact_paths()
    return OperatorPaths(
        defaults.ai_config_path,
        defaults.registry_path,
        defaults.promoted_path,
        defaults.spec_dir,
        defaults.audit_log_path,
    )


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
    path.write_text(
        json.dumps(safe_config.to_json_object(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return safe_config


@dataclass(frozen=True, slots=True)
class _LocalBootstrapResearchRunner:
    def is_available(self) -> bool:
        return True

    def run(self, query: str) -> ResearchResult:
        research_id = _local_research_id(query)
        source_id = research_id.replace("research", "source", 1)
        return ResearchResult(
            research_id=research_id,
            provider="insane_search",
            query=query,
            created_at="2026-07-11T00:00:00+09:00",
            sources=(
                SourceMetadata(
                    source_id,
                    "로컬 부트스트랩 검증 근거",
                    "local://ai-quant-bootstrap",
                    "2026-07-11",
                    "로컬 학습 버튼이 사용하는 기본 연구 근거입니다.",
                ),
            ),
            summary="로컬 부트스트랩 학습은 실주문 없이 검증용 후보를 생성합니다.",
            usable=True,
            failure_reason="",
        )


@dataclass(frozen=True, slots=True)
class _LocalBootstrapSpecProvider:
    def request_strategy_specs(
        self,
        prompt: str,
        context: ResearchContext,
    ) -> tuple[str, ...]:
        del prompt, context
        return (json.dumps(_bootstrap_strategy_payload(), ensure_ascii=False),)


def _local_research_id(query: str) -> str:
    if "trend_following" in query:
        return "local-research-trend-following"
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
    return f"local-research-{digest}"


def _bootstrap_strategy_payload() -> dict[str, JsonValue]:
    return {
        "strategy_id": "local_bootstrap_trend",
        "version": "v1",
        "strategy_family": "trend_following",
        "description": "실주문 없이 자동 학습을 시작하기 위한 로컬 추세 추종 검증 후보",
        "research_basis": {
            "provider": "insane_search",
            "research_ids": ["local-research-trend-following"],
            "source_ids": ["local-source-trend-following"],
            "summary": "로컬 부트스트랩 연구 근거를 사용한 검증 후보",
        },
        "signals": [
            {"type": "trend_following", "lookback_days": 20, "weight": 1.0},
        ],
        "entry_rule": {"type": "weighted_score", "threshold": 0.2, "top_n": 1},
        "exit_rule": {
            "stop_loss_mode": "atr_multiple",
            "stop_loss_atr_multiple": 2.0,
            "take_profit_mode": "atr_multiple",
            "take_profit_atr_multiple": 1_000_000.0,
            "trailing_stop": False,
            "max_holding_days": 300,
        },
        "position_sizing": {
            "method": "volatility_target",
            "risk_per_trade_pct": 0.001,
            "confidence_adjusted": True,
            "max_single_position_pct": 0.02,
        },
        "risk_controls": {
            "use_kill_switch": True,
            "block_if_data_stale": True,
            "block_if_spread_abnormal": True,
            "block_if_daily_loss_limit": True,
            "block_before_market_close": True,
        },
        "metadata": {
            "created_by": "ai_quant_lab",
            "created_at": "2026-07-11T00:00:00+09:00",
        },
    }


def _local_bars_by_symbol() -> BarsBySymbol:
    return {
        "QQQ": _local_price_bars("QQQ", 0.003),
        "AAPL": _local_price_bars("AAPL", 0.01),
    }


def _local_price_bars(symbol: str, daily_drift: float) -> list[PriceBar]:
    output: list[PriceBar] = []
    price = 100.0
    for index in range(320):
        price *= 1.0 + daily_drift
        timestamp = (date(2024, 1, 1) + timedelta(days=index)).isoformat()
        output.append(
            PriceBar(
                symbol,
                timestamp,
                price * 0.999,
                price * 1.003,
                price * 0.997,
                price,
                1_000_000 + index,
                bid=price - 0.01,
                ask=price + 0.01,
            )
        )
    return output
