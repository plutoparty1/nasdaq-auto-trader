import json
from pathlib import Path

import pytest

from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.ai_quant_lab.backtest_engine import BacktestEngine
from nasdaq_auto_trader.ai_quant_lab.config import AIQuantConfig
from nasdaq_auto_trader.ai_quant_lab.insane_search_research import InsaneSearchResearchService
from nasdaq_auto_trader.ai_quant_lab.registry import StrategyRegistry
from nasdaq_auto_trader.ai_quant_lab.scoring_engine import ScoringEngine
from nasdaq_auto_trader.ai_quant_lab.candidate_evaluation import CandidateEvaluationPipeline
from nasdaq_auto_trader.ai_quant_lab.self_improvement_loop import SelfImprovementLoop
from nasdaq_auto_trader.ai_quant_lab.strategy_factory import AIStrategyFactory
from nasdaq_auto_trader.ai_quant_lab.validation_engine import ValidationEngine
from tests.ai_quant_fixtures import FakeRunner, FakeSpecProvider, bars, valid_spec, valid_spec_payload


@pytest.mark.parametrize(
    "pipeline_type", (CandidateEvaluationPipeline, SelfImprovementLoop), ids=("current", "legacy"),
)
def test_disabled_research_preserves_public_reason_without_generating(
    tmp_path: Path, pipeline_type: type[CandidateEvaluationPipeline],
) -> None:
    # Given: research evaluation is disabled through the persisted compatibility flag.
    config = AIQuantConfig(ai_quant_lab_enabled=True, self_improvement_enabled=False)
    provider = FakeSpecProvider(())
    audit = NullAuditLogger()
    pipeline = pipeline_type(
        config,
        InsaneSearchResearchService(config=config, runner=FakeRunner()),
        AIStrategyFactory(provider),
        BacktestEngine(config),
        ValidationEngine(),
        ScoringEngine(),
        StrategyRegistry(tmp_path / "registry.json", tmp_path / "promoted.json", config),
        audit,
    )

    # When: an operator requests one candidate evaluation.
    result = pipeline.run_once({})

    # Then: both imports preserve the public reason and do not invoke generation.
    assert result.status == "aborted"
    assert result.reasons == ("self_improvement_disabled",)
    assert audit.events[-1].event_type == "candidate_evaluation_aborted"
    assert provider.calls == 0


def test_candidate_evaluation_preserves_provenance_and_manual_live_gate(tmp_path: Path) -> None:
    # Given: sourced candidate specifications and historical prices, with no broker connection.
    config = AIQuantConfig(ai_quant_lab_enabled=True, self_improvement_enabled=True)
    registry = StrategyRegistry(tmp_path / "registry.json", tmp_path / "promoted.json", config)
    pipeline = CandidateEvaluationPipeline(
        config,
        InsaneSearchResearchService(config=config, runner=FakeRunner()),
        AIStrategyFactory(FakeSpecProvider((json.dumps(valid_spec_payload()),))),
        BacktestEngine(config),
        ValidationEngine(),
        ScoringEngine(),
        registry,
    )

    # When: the real research, validation and registry workflow evaluates the candidate.
    result = pipeline.run_once({"QQQ": bars("QQQ"), "AAPL": bars("AAPL")})

    # Then: research provenance survives and the candidate has no live execution authority.
    assert result.status == "completed"
    assert result.generated_candidates == 1
    records = registry.load_records()
    assert len(records) == 1
    assert records[0].research_basis == valid_spec().research_basis
    assert records[0].manual_approval is False
    assert records[0].allowed_for_live is False
    assert registry.load_promoted_strategy() is None
