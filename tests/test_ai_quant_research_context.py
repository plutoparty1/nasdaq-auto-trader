import unittest
import json
from typing import Final

from tests.ai_quant_fixtures import FakeRunner, FakeSpecProvider, valid_spec_payload
from nasdaq_auto_trader.ai_quant_lab.audit_logger import NullAuditLogger
from nasdaq_auto_trader.ai_quant_lab.insane_search_research import (
    InsaneSearchResearchService,
    ResearchContext,
    ResearchResult,
    SourceMetadata,
    failed_research_result,
    validate_research_sources,
)
from nasdaq_auto_trader.ai_quant_lab.strategy_factory import AIStrategyFactory
from nasdaq_auto_trader.ai_quant_lab.strategy_schema import allowed_strategy_families


REQUIRED_STRATEGY_FAMILIES: Final[frozenset[str]] = frozenset(
    {
        "trend_following",
        "cross_sectional_momentum",
        "time_series_momentum",
        "mean_reversion",
        "bollinger_zscore",
        "rsi_oscillator",
        "volatility_breakout",
        "breakout",
        "pair_trading_stat_arb",
        "factor_strategy",
        "sector_theme_rotation",
        "volatility_targeting",
        "ensemble",
    }
)


class MissingSourceRunner(FakeRunner):
    def run(self, query: str) -> ResearchResult:
        if "mean_reversion" in query:
            self.calls.append(query)
            return failed_research_result(query, "insane_search_sources_missing")
        return super().run(query)


class DuplicateIdentityRunner(FakeRunner):
    def run(self, query: str) -> ResearchResult:
        result = super().run(query)
        return ResearchResult(
            research_id="duplicate-research-id",
            provider=result.provider,
            query=result.query,
            created_at=result.created_at,
            sources=(
                SourceMetadata(
                    "duplicate-source-id",
                    result.sources[0].title,
                    result.sources[0].url,
                    result.sources[0].published_at,
                    result.sources[0].summary,
                ),
            ),
            summary=result.summary,
            usable=result.usable,
            failure_reason=result.failure_reason,
        )


class SpoofedProviderRunner(FakeRunner):
    def run(self, query: str) -> ResearchResult:
        result = super().run(query)
        return ResearchResult(
            research_id=result.research_id,
            provider="attacker_controlled_provider",
            query=result.query,
            created_at=result.created_at,
            sources=result.sources,
            summary=result.summary,
            usable=result.usable,
            failure_reason=result.failure_reason,
        )


class AIQuantResearchContextTests(unittest.TestCase):
    def test_strategy_family_whitelist_matches_required_quant_families(self):
        self.assertEqual(set(allowed_strategy_families()), REQUIRED_STRATEGY_FAMILIES)

    def test_research_context_queries_every_required_strategy_family(self):
        expected_queries = {
            f"quant trading evidence for {family} NASDAQ strategy validation"
            for family in REQUIRED_STRATEGY_FAMILIES
        }
        runner = FakeRunner()
        service = InsaneSearchResearchService(runner=runner)

        context = service.build_research_context_for_strategy_generation()
        strategy_queries = {
            query
            for query in runner.calls
            if query.startswith("quant trading evidence for ")
        }

        self.assertEqual(strategy_queries, expected_queries)
        self.assertGreaterEqual(len(context.results), len(REQUIRED_STRATEGY_FAMILIES))

    def test_research_context_rejects_partial_family_source_failure(self):
        audit = NullAuditLogger()
        service = InsaneSearchResearchService(
            runner=MissingSourceRunner(),
            audit_logger=audit,
        )

        context = service.build_research_context_for_strategy_generation()

        self.assertFalse(validate_research_sources(context))
        self.assertIn("research_context_rejected", [event.event_type for event in audit.events])

    def test_research_context_rejects_duplicate_research_or_source_ids(self):
        audit = NullAuditLogger()
        service = InsaneSearchResearchService(
            runner=DuplicateIdentityRunner(),
            audit_logger=audit,
        )

        context = service.build_research_context_for_strategy_generation()

        self.assertFalse(validate_research_sources(context))
        self.assertIn("research_context_rejected", [event.event_type for event in audit.events])

    def test_research_context_rejects_result_provider_spoofing(self):
        context = InsaneSearchResearchService(
            runner=SpoofedProviderRunner(),
        ).build_research_context_for_strategy_generation()
        audit = NullAuditLogger()
        factory = AIStrategyFactory(
            FakeSpecProvider([json.dumps(valid_spec_payload())]),
            audit_logger=audit,
        )

        result = factory.generate_candidates(context, 1)

        self.assertFalse(validate_research_sources(context))
        self.assertEqual(result.accepted, ())
        self.assertIn("research_context_invalid", result.rejected_reasons)

    def test_research_context_rejects_incomplete_source_metadata(self):
        context = ResearchContext(
            "insane_search",
            (
                ResearchResult(
                    research_id="research-1",
                    provider="insane_search",
                    query="query",
                    created_at="2026-07-01T00:00:00+09:00",
                    sources=(
                        SourceMetadata(
                            "source-1",
                            "",
                            "",
                            "2026-01-01",
                            "summary",
                        ),
                    ),
                    summary="summary",
                    usable=True,
                    failure_reason="",
                ),
            ),
            "summary",
        )

        self.assertFalse(validate_research_sources(context))

    def test_strategy_factory_rejects_research_basis_ids_outside_context(self):
        payload = valid_spec_payload()
        payload["research_basis"] = {
            "provider": "insane_search",
            "research_ids": ["spoofed-research-id"],
            "source_ids": ["spoofed-source-id"],
            "summary": "spoofed",
        }
        context = InsaneSearchResearchService(
            runner=FakeRunner(),
        ).build_research_context_for_strategy_generation()
        audit = NullAuditLogger()
        factory = AIStrategyFactory(
            FakeSpecProvider([json.dumps(payload)]),
            audit_logger=audit,
        )

        result = factory.generate_candidates(context, 1)

        self.assertEqual(result.accepted, ())
        self.assertIn("research_basis_research_ids_not_in_context", result.rejected_reasons)
        self.assertIn("research_basis_source_ids_not_in_context", result.rejected_reasons)
        self.assertIn(
            "ai_strategy_research_basis_rejected",
            [event.event_type for event in audit.events],
        )


if __name__ == "__main__":
    unittest.main()
