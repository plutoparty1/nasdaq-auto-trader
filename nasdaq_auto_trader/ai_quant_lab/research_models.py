from __future__ import annotations

from dataclasses import dataclass

from .types import JsonObject


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source_id: str
    title: str
    url: str
    published_at: str
    summary: str


@dataclass(frozen=True, slots=True)
class ResearchResult:
    research_id: str
    provider: str
    query: str
    created_at: str
    sources: tuple[SourceMetadata, ...]
    summary: str
    usable: bool
    failure_reason: str

    def to_json_object(self) -> JsonObject:
        return {
            "research_id": self.research_id,
            "provider": self.provider,
            "query": self.query,
            "created_at": self.created_at,
            "sources": [
                {
                    "source_id": source.source_id,
                    "title": source.title,
                    "url": source.url,
                    "published_at": source.published_at,
                    "summary": source.summary,
                }
                for source in self.sources
            ],
            "summary": self.summary,
            "usable": self.usable,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True, slots=True)
class ResearchContext:
    provider: str
    results: tuple[ResearchResult, ...]
    summary: str

    @property
    def research_ids(self) -> tuple[str, ...]:
        return tuple(result.research_id for result in self.results if result.usable)

    @property
    def source_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for result in self.results:
            ids.extend(source.source_id for source in result.sources)
        return tuple(ids)
