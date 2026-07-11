from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .audit_logger import AuditEvent, NullAuditLogger
from .config import AIQuantConfig, INSANE_SEARCH_PROVIDER
from .research_models import ResearchContext, ResearchResult, SourceMetadata
from .storage import safe_artifact_path
from .strategy_schema import allowed_strategy_families
from .types import JsonObject, JsonValue


class InsaneSearchRunner(Protocol):
    def is_available(self) -> bool: ...

    def run(self, query: str) -> ResearchResult: ...


class DisabledInsaneSearchRunner:
    def is_available(self) -> bool:
        return False

    def run(self, query: str) -> ResearchResult:
        return failed_research_result(query, "insane_search_unavailable")


class CommandInsaneSearchRunner:
    def __init__(self, command: tuple[str, ...], timeout_seconds: int = 60) -> None:
        self.command = command
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        return bool(self.command)

    def run(self, query: str) -> ResearchResult:
        try:
            completed = subprocess.run(
                [*self.command, query],
                capture_output=True,
                check=False,
                encoding="utf-8",
                env=_research_command_environment(),
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return failed_research_result(query, "insane_search_command_timed_out")
        except OSError:
            return failed_research_result(query, "insane_search_command_unavailable")
        if completed.returncode != 0:
            return failed_research_result(query, "insane_search_command_failed")
        return _research_result_from_command_json(query, completed.stdout)


class InsaneSearchResearchService:
    def __init__(
        self,
        config: AIQuantConfig | None = None,
        runner: InsaneSearchRunner | None = None,
        audit_logger: NullAuditLogger | None = None,
        result_dir: str | Path | None = None,
    ) -> None:
        self.config = config or AIQuantConfig()
        self.runner = runner or DisabledInsaneSearchRunner()
        self.audit_logger = audit_logger or NullAuditLogger()
        self.result_dir = Path(result_dir) if result_dir is not None else None

    def is_available(self) -> bool:
        return (
            self.config.research_provider == INSANE_SEARCH_PROVIDER
            and self.config.allow_only_insane_search_for_research
            and self.runner.is_available()
        )

    def run_quant_research(self, query: str) -> ResearchResult:
        self.audit_logger.append(
            AuditEvent("insane_search_requested", payload={"query": query})
        )
        if not self.is_available():
            result = failed_research_result(query, "insane_search_unavailable")
            self.audit_logger.append(
                AuditEvent(
                    "insane_search_failed",
                    severity="error",
                    payload={"query": query},
                    research_id=result.research_id,
                    error=result.failure_reason,
                )
            )
            self._save_result(result)
            return result
        result = self.runner.run(query)
        event_type = "insane_search_completed" if result.usable else "insane_search_failed"
        self.audit_logger.append(
            AuditEvent(
                event_type,
                payload={"query": query, "source_count": len(result.sources)},
                research_id=result.research_id,
                source_ids=tuple(source.source_id for source in result.sources),
                error=result.failure_reason or None,
            )
        )
        self._save_result(result)
        return result

    def research_strategy_family(self, strategy_family: str) -> ResearchResult:
        return self.run_quant_research(
            f"quant trading evidence for {strategy_family} NASDAQ strategy validation"
        )

    def research_validation_method(self, method_name: str) -> ResearchResult:
        return self.run_quant_research(
            f"quant backtest validation method {method_name} overfitting prevention"
        )

    def research_market_regime_methods(self) -> ResearchResult:
        return self.run_quant_research(
            "market regime detection methods for equity trading validation"
        )

    def build_research_context_for_strategy_generation(self) -> ResearchContext:
        results = (
            *(
                self.research_strategy_family(strategy_family)
                for strategy_family in allowed_strategy_families()
            ),
            self.research_validation_method("walk forward validation"),
            self.research_market_regime_methods(),
        )
        summary = "\n".join(result.summary for result in results if result.usable and result.summary)
        context = ResearchContext(INSANE_SEARCH_PROVIDER, results, summary)
        event = (
            "research_context_created"
            if validate_research_sources(context)
            else "research_context_rejected"
        )
        self.audit_logger.append(
            AuditEvent(event, payload={"research_ids": list(context.research_ids)})
        )
        return context

    def _save_result(self, result: ResearchResult) -> None:
        if self.result_dir is None:
            return
        self.result_dir.mkdir(parents=True, exist_ok=True)
        path = safe_artifact_path(self.result_dir, result.research_id, ".json")
        path.write_text(json.dumps(result.to_json_object(), indent=2), encoding="utf-8")


def validate_research_sources(context: ResearchContext) -> bool:
    research_ids = context.research_ids
    source_ids = context.source_ids
    return (
        context.provider == INSANE_SEARCH_PROVIDER
        and bool(context.results)
        and all(_result_has_identifiable_sources(result) for result in context.results)
        and bool(research_ids)
        and bool(source_ids)
        and _unique_nonempty(research_ids)
        and _unique_nonempty(source_ids)
    )


def _result_has_identifiable_sources(result: ResearchResult) -> bool:
    return (
        result.usable
        and result.provider == INSANE_SEARCH_PROVIDER
        and bool(result.research_id.strip())
        and bool(result.sources)
        and all(
            source.source_id.strip() and source.title.strip() and source.url.strip()
            for source in result.sources
        )
    )


def _unique_nonempty(values: tuple[str, ...]) -> bool:
    cleaned = tuple(value.strip() for value in values)
    return all(cleaned) and len(cleaned) == len(set(cleaned))


def failed_research_result(query: str, reason: str) -> ResearchResult:
    return ResearchResult(
        research_id=str(uuid4()),
        provider=INSANE_SEARCH_PROVIDER,
        query=query,
        created_at=datetime.now(timezone.utc).isoformat(),
        sources=(),
        summary="",
        usable=False,
        failure_reason=reason or "insane_search_failed",
    )


def _research_result_from_command_json(query: str, raw: str) -> ResearchResult:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return failed_research_result(query, "insane_search_invalid_json")
    if not isinstance(payload, dict):
        return failed_research_result(query, "insane_search_invalid_payload")
    sources = _sources_from_payload(payload)
    summary = _string(payload.get("summary"))
    return ResearchResult(
        research_id=_string(payload.get("research_id")) or str(uuid4()),
        provider=INSANE_SEARCH_PROVIDER,
        query=query,
        created_at=datetime.now(timezone.utc).isoformat(),
        sources=tuple(sources),
        summary=summary,
        usable=bool(sources),
        failure_reason="" if sources else "insane_search_sources_missing",
    )


def _sources_from_payload(payload: dict[str, JsonValue]) -> list[SourceMetadata]:
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        return []
    sources: list[SourceMetadata] = []
    for index, item in enumerate(raw_sources, start=1):
        if not isinstance(item, dict):
            continue
        url = _string(item.get("url"))
        title = _string(item.get("title"))
        if not url or not title:
            continue
        sources.append(
            SourceMetadata(
                source_id=_string(item.get("source_id")) or f"source_{index}",
                title=title,
                url=url,
                published_at=_string(item.get("published_at")),
                summary=_string(item.get("summary")),
            )
        )
    return sources


def _string(value: JsonValue | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def _research_command_environment() -> dict[str, str]:
    allowed = {
        "APPDATA",
        "COMSPEC",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in allowed or key.upper().startswith("INSANE_SEARCH_")
    }
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment
