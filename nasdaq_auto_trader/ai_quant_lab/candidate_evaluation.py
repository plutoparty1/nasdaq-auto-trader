from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from .audit_logger import AuditEvent, NullAuditLogger
from .backtest_engine import BacktestEngine, BacktestRequest
from .config import AIQuantConfig, validate_ai_quant_config
from .insane_search_research import (
    InsaneSearchResearchService,
    ResearchContext,
    validate_research_sources,
)
from .post_trade_feedback import PostTradeFeedback
from .registry import StrategyRegistry
from .scoring_engine import ScoringEngine
from .strategy_factory import AIStrategyFactory
from .validation_engine import ValidationEngine
from nasdaq_auto_trader.quant_data.features import PriceBar


@dataclass(frozen=True, slots=True)
class CandidateEvaluationResult:
    status: str
    experiment_id: str
    generated_candidates: int
    accepted_candidates: int
    reasons: tuple[str, ...]


class CandidateEvaluationPipeline:
    """Evaluate research candidates without model training or automatic live promotion."""

    def __init__(
        self,
        config: AIQuantConfig,
        research_service: InsaneSearchResearchService,
        strategy_factory: AIStrategyFactory,
        backtest_engine: BacktestEngine,
        validation_engine: ValidationEngine,
        scoring_engine: ScoringEngine,
        registry: StrategyRegistry,
        audit_logger: NullAuditLogger | None = None,
    ) -> None:
        self.config = config
        self.research_service = research_service
        self.strategy_factory = strategy_factory
        self.backtest_engine = backtest_engine
        self.validation_engine = validation_engine
        self.scoring_engine = scoring_engine
        self.registry = registry
        self.audit_logger = audit_logger or NullAuditLogger()

    def run_once(
        self,
        bars_by_symbol: dict[str, list[PriceBar]],
        champion_metrics: dict[str, float] | None = None,
        post_trade_feedback: PostTradeFeedback | None = None,
    ) -> CandidateEvaluationResult:
        experiment_id = str(uuid4())
        config_validation = validate_ai_quant_config(self.config)
        if not config_validation.valid:
            return self._abort(experiment_id, config_validation.reasons)
        # Persisted configuration keeps the legacy key; it enables candidate evaluation only.
        if not self.config.ai_quant_lab_enabled or not self.config.self_improvement_enabled:
            return self._abort(experiment_id, ("self_improvement_disabled",))
        if not self.research_service.is_available():
            self.audit_logger.append(
                AuditEvent(
                    "insane_search_unavailable",
                    severity="error",
                    experiment_id=experiment_id,
                )
            )
            return self._abort(experiment_id, ("insane_search_unavailable",))
        context = self.research_service.build_research_context_for_strategy_generation()
        if not validate_research_sources(context):
            return self._abort(experiment_id, ("research_sources_missing",))
        context = _context_with_feedback(context, post_trade_feedback)
        factory_result = self.strategy_factory.generate_candidates(
            context,
            self.config.max_strategy_candidates_per_run,
        )
        accepted = 0
        rejection_reasons = list(factory_result.rejected_reasons)
        for spec in factory_result.accepted:
            self.registry.register_schema_validated(spec)
            backtest = self.backtest_engine.run(BacktestRequest(spec, bars_by_symbol))
            validation = self.validation_engine.validate(backtest)
            score = self.scoring_engine.score(backtest, validation, champion_metrics)
            decision = self.registry.evaluate_promotion(spec, score)
            if decision.allowed:
                accepted += 1
            else:
                rejection_reasons.extend(score.rejection_reasons)
                rejection_reasons.extend(decision.reasons)
        self.audit_logger.append(
            AuditEvent(
                "strategy_rejected" if accepted == 0 else "promotion_evaluated",
                experiment_id=experiment_id,
                payload={"accepted": accepted, "candidates": len(factory_result.accepted)},
            )
        )
        return CandidateEvaluationResult(
            status="completed",
            experiment_id=experiment_id,
            generated_candidates=len(factory_result.accepted) + len(factory_result.rejected_reasons),
            accepted_candidates=accepted,
            reasons=tuple(dict.fromkeys(rejection_reasons)),
        )

    def _abort(
        self,
        experiment_id: str,
        reasons: tuple[str, ...],
    ) -> CandidateEvaluationResult:
        self.audit_logger.append(
            AuditEvent(
                "candidate_evaluation_aborted",
                severity="warning",
                experiment_id=experiment_id,
                payload={"reasons": list(reasons)},
            )
        )
        return CandidateEvaluationResult(
            status="aborted",
            experiment_id=experiment_id,
            generated_candidates=0,
            accepted_candidates=0,
            reasons=reasons,
        )


def _context_with_feedback(
    context: ResearchContext,
    feedback: PostTradeFeedback | None,
) -> ResearchContext:
    if feedback is None:
        return context
    summary = f"{context.summary}\n\nPost-trade feedback (descriptive observations, not model training):\n{feedback.to_prompt_feedback()}"
    return ResearchContext(context.provider, context.results, summary)
