from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from rag.index.store import EmbeddingIndexStore


@dataclass(frozen=True)
class RetrievalPolicyConfig:
    enabled: bool = True
    top_k: int = 3
    min_relevance_score: float = 0.2
    allow_global_fallback: bool = True


@dataclass(frozen=True)
class RetrievedSource:
    chunk_id: str
    source_path: str
    source_type: str
    task_id: str | None
    run_id: str | None
    relevance_score: float
    text: str


@dataclass(frozen=True)
class RetrievalResult:
    use_case: str
    query: str
    enabled: bool
    top_k: int
    min_relevance_score: float
    sources: tuple[RetrievedSource, ...]


def policy_from_mapping(
    value: Mapping[str, Any] | None,
    *,
    base: RetrievalPolicyConfig,
) -> RetrievalPolicyConfig:
    if value is None:
        return base

    enabled = base.enabled
    top_k = base.top_k
    min_relevance_score = base.min_relevance_score
    allow_global_fallback = base.allow_global_fallback

    raw_enabled = value.get("enabled")
    if isinstance(raw_enabled, bool):
        enabled = raw_enabled

    raw_top_k = value.get("top_k")
    if isinstance(raw_top_k, int):
        top_k = max(0, raw_top_k)

    raw_min = value.get("min_relevance_score")
    if isinstance(raw_min, (int, float)):
        min_relevance_score = float(raw_min)

    raw_fallback = value.get("allow_global_fallback")
    if isinstance(raw_fallback, bool):
        allow_global_fallback = raw_fallback

    return RetrievalPolicyConfig(
        enabled=enabled,
        top_k=top_k,
        min_relevance_score=min_relevance_score,
        allow_global_fallback=allow_global_fallback,
    )


class PolicyAwareRetriever:
    def __init__(self, *, index_path: str | Path | None = None) -> None:
        self.index_path = Path(index_path).expanduser() if index_path else None
        self._store: EmbeddingIndexStore | None = None

    def retrieve(
        self,
        *,
        use_case: str,
        query: str,
        task_id: str | None,
        run_id: str | None,
        policy: RetrievalPolicyConfig,
    ) -> RetrievalResult:
        normalized_query = query.strip()
        if not normalized_query:
            return RetrievalResult(
                use_case=use_case,
                query="",
                enabled=False,
                top_k=policy.top_k,
                min_relevance_score=policy.min_relevance_score,
                sources=(),
            )

        if not policy.enabled or policy.top_k <= 0:
            return RetrievalResult(
                use_case=use_case,
                query=normalized_query,
                enabled=False,
                top_k=policy.top_k,
                min_relevance_score=policy.min_relevance_score,
                sources=(),
            )

        store = self._load_store()
        if store is None:
            return RetrievalResult(
                use_case=use_case,
                query=normalized_query,
                enabled=True,
                top_k=policy.top_k,
                min_relevance_score=policy.min_relevance_score,
                sources=(),
            )

        scoped_hits = store.search(
            normalized_query,
            top_k=policy.top_k,
            task_id=task_id,
            run_id=run_id,
        )
        hits = scoped_hits
        if not hits and policy.allow_global_fallback:
            hits = store.search(normalized_query, top_k=policy.top_k)

        filtered = [hit for hit in hits if hit.score >= policy.min_relevance_score]
        sources = tuple(
            RetrievedSource(
                chunk_id=hit.chunk_id,
                source_path=hit.source_path,
                source_type=hit.source_type,
                task_id=hit.task_id,
                run_id=hit.run_id,
                relevance_score=hit.score,
                text=hit.text,
            )
            for hit in filtered
        )
        return RetrievalResult(
            use_case=use_case,
            query=normalized_query,
            enabled=True,
            top_k=policy.top_k,
            min_relevance_score=policy.min_relevance_score,
            sources=sources,
        )

    def _load_store(self) -> EmbeddingIndexStore | None:
        if self._store is not None:
            return self._store
        if self.index_path is None or not self.index_path.is_file():
            return None
        self._store = EmbeddingIndexStore.load(self.index_path)
        return self._store
