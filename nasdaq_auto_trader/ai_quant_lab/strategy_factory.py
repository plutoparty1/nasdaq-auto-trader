from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .audit_logger import AuditEvent, NullAuditLogger
from .insane_search_research import ResearchContext, validate_research_sources
from .storage import safe_artifact_path
from .strategy_schema import StrategySpec, parse_strategy_spec_json


class StrategySpecProvider(Protocol):
    def request_strategy_specs(self, prompt: str, context: ResearchContext) -> tuple[str, ...]:
        ...


@dataclass(frozen=True, slots=True)
class StrategyFactoryResult:
    accepted: tuple[StrategySpec, ...]
    rejected_reasons: tuple[str, ...]


class AIStrategyFactory:
    def __init__(
        self,
        provider: StrategySpecProvider,
        audit_logger: NullAuditLogger | None = None,
        output_dir: str | Path | None = None,
    ) -> None:
        self.provider = provider
        self.audit_logger = audit_logger or NullAuditLogger()
        self.output_dir = Path(output_dir) if output_dir is not None else None

    def generate_candidates(
        self,
        context: ResearchContext,
        max_candidates: int,
    ) -> StrategyFactoryResult:
        if not validate_research_sources(context):
            return StrategyFactoryResult((), ("research_context_invalid",))
        prompt = build_strategy_prompt(context, max_candidates)
        audit_ok = self.audit_logger.append(
            AuditEvent(
                "ai_strategy_requested",
                payload={"max_candidates": max_candidates},
                source_ids=context.source_ids,
            )
        )
        if not audit_ok:
            return StrategyFactoryResult((), ("audit_log_write_failed",))
        raw_candidates = self.provider.request_strategy_specs(prompt, context)
        accepted: list[StrategySpec] = []
        rejected: list[str] = []
        for raw in raw_candidates[:max_candidates]:
            audit_ok = self.audit_logger.append(
                AuditEvent("ai_strategy_response_received", payload={"bytes": len(raw)})
            )
            if not audit_ok:
                rejected.append("audit_log_write_failed")
                break
            validation = parse_strategy_spec_json(raw)
            if validation.spec is None:
                rejected.extend(validation.reasons)
                if not self.audit_logger.append(
                    AuditEvent(
                        "ai_strategy_schema_rejected",
                        severity="warning",
                        payload={"reasons": list(validation.reasons)},
                    )
                ):
                    rejected.append("audit_log_write_failed")
                    break
                continue
            research_basis_reasons = research_basis_context_rejection_reasons(
                validation.spec,
                context,
            )
            if research_basis_reasons:
                rejected.extend(research_basis_reasons)
                if not self.audit_logger.append(
                    AuditEvent(
                        "ai_strategy_research_basis_rejected",
                        severity="warning",
                        payload={"reasons": list(research_basis_reasons)},
                        strategy_id=validation.spec.strategy_id,
                        strategy_version=validation.spec.version,
                    )
                ):
                    rejected.append("audit_log_write_failed")
                    break
                continue
            accepted.append(validation.spec)
            if not self.audit_logger.append(
                AuditEvent(
                    "ai_strategy_schema_validated",
                    strategy_id=validation.spec.strategy_id,
                    strategy_version=validation.spec.version,
                )
            ):
                accepted.pop()
                rejected.append("audit_log_write_failed")
                break
            self._save_spec(validation.spec)
        return StrategyFactoryResult(tuple(accepted), tuple(rejected))

    def _save_spec(self, spec: StrategySpec) -> None:
        if self.output_dir is None:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = safe_artifact_path(self.output_dir, f"{spec.strategy_id}-{spec.version}", ".json")
        path.write_text(json.dumps(spec.raw, indent=2), encoding="utf-8")


def research_basis_context_rejection_reasons(
    spec: StrategySpec,
    context: ResearchContext,
) -> tuple[str, ...]:
    reasons: list[str] = []
    context_research_ids = set(context.research_ids)
    context_source_ids = set(context.source_ids)
    if not set(spec.research_basis.research_ids).issubset(context_research_ids):
        reasons.append("research_basis_research_ids_not_in_context")
    if not set(spec.research_basis.source_ids).issubset(context_source_ids):
        reasons.append("research_basis_source_ids_not_in_context")
    return tuple(reasons)


def build_strategy_prompt(context: ResearchContext, max_candidates: int) -> str:
    research_ids = ", ".join(context.research_ids)
    source_ids = ", ".join(context.source_ids)
    return (
        "Return JSON only. No markdown, code fences, Python, orders, tickers as "
        "orders, or dynamic code. Generate at most "
        f"{max_candidates} StrategySpec candidates using only whitelisted strategy "
        "families. Every StrategySpec must cite research_basis.provider=insane_search, "
        f"research_ids=[{research_ids}], and source_ids=[{source_ids}]. "
        "Avoid look-ahead bias, excessive parameters, and direct order sizing. "
        f"Research summary:\n{context.summary}"
    )
