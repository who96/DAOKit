from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from rag.index.providers import (
    EmbeddingProviderConfig,
    PRODUCTION_EMBEDDING_MODE,
    local_embedding_candidates,
    optional_api_embedding_candidates,
)
from rag.index.store import ChunkForIndex, EmbeddingIndexStore


_DATASET_SCHEMA_VERSION = "rag-benchmark.v1"
_METRICS_SCHEMA_VERSION = "retrieval-benchmark.v1"
_DEFAULT_TOP_KS = (1, 3, 5)

DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parent / "datasets" / "dkt-061-retrieval-benchmark-v1.json"
)


@dataclass(frozen=True)
class BenchmarkChunk:
    chunk_id: str
    text: str
    source_path: str
    source_type: str
    task_id: str | None
    run_id: str | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "source_path": self.source_path,
            "source_type": self.source_type,
            "task_id": self.task_id,
            "run_id": self.run_id,
        }


@dataclass(frozen=True)
class BenchmarkQuery:
    query_id: str
    query: str
    relevant_chunk_ids: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "query": self.query,
            "relevant_chunk_ids": list(self.relevant_chunk_ids),
        }


@dataclass(frozen=True)
class BenchmarkDataset:
    schema_version: str
    dataset_id: str
    description: str
    top_ks: tuple[int, ...]
    chunks: tuple[BenchmarkChunk, ...]
    queries: tuple[BenchmarkQuery, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "description": self.description,
            "top_ks": list(self.top_ks),
            "chunks": [chunk.to_payload() for chunk in self.chunks],
            "queries": [query.to_payload() for query in self.queries],
        }


@dataclass(frozen=True)
class QueryBenchmarkResult:
    query_id: str
    query: str
    relevant_chunk_ids: tuple[str, ...]
    retrieved_chunk_ids: tuple[str, ...]
    first_relevant_rank: int | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "query": self.query,
            "relevant_chunk_ids": list(self.relevant_chunk_ids),
            "retrieved_chunk_ids": list(self.retrieved_chunk_ids),
            "first_relevant_rank": self.first_relevant_rank,
        }


@dataclass(frozen=True)
class BenchmarkBackendResult:
    backend_id: str
    provider_name: str
    status: str
    metrics: Mapping[str, float]
    query_results: tuple[QueryBenchmarkResult, ...]
    error: str | None = None
    rank: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "provider_name": self.provider_name,
            "status": self.status,
            "rank": self.rank,
            "metrics": {key: float(value) for key, value in sorted(self.metrics.items())},
            "error": self.error,
            "queries": [result.to_payload() for result in self.query_results],
        }


@dataclass(frozen=True)
class RetrievalBenchmarkRunResult:
    schema_version: str
    task_id: str
    run_id: str
    dataset: BenchmarkDataset
    top_ks: tuple[int, ...]
    dimensions: int
    backend_results: tuple[BenchmarkBackendResult, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "dimensions": self.dimensions,
            "top_ks": list(self.top_ks),
            "dataset_id": self.dataset.dataset_id,
            "query_count": len(self.dataset.queries),
            "chunk_count": len(self.dataset.chunks),
            "backends": [result.to_payload() for result in self.backend_results],
        }


@dataclass(frozen=True)
class BenchmarkArtifactPaths:
    dataset_path: Path
    metrics_path: Path
    report_path: Path


def default_backend_ids(*, include_optional_api: bool = False) -> tuple[str, ...]:
    backends = list(local_embedding_candidates())
    if include_optional_api:
        backends.extend(optional_api_embedding_candidates())
    return tuple(backends)


def load_benchmark_dataset(path: str | Path) -> BenchmarkDataset:
    dataset_path = Path(path)
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    return _parse_dataset(payload)


def run_retrieval_benchmark(
    *,
    dataset: BenchmarkDataset,
    backend_ids: Sequence[str] | None = None,
    top_ks: Sequence[int] | None = None,
    dimensions: int = 64,
    task_id: str = "DKT-061",
    run_id: str = "manual",
) -> RetrievalBenchmarkRunResult:
    if dimensions <= 0:
        raise ValueError("dimensions must be > 0")
    resolved_top_ks = _normalize_top_ks(top_ks or dataset.top_ks)
    if not resolved_top_ks:
        raise ValueError("at least one top-k threshold is required")

    candidate_backends = tuple(backend_ids or default_backend_ids())
    if not candidate_backends:
        raise ValueError("at least one backend id is required")

    chunk_payloads = _to_index_chunks(dataset.chunks)
    backend_results: list[BenchmarkBackendResult] = []
    for backend_id in candidate_backends:
        try:
            store = EmbeddingIndexStore.from_chunks(
                chunk_payloads,
                dimensions=dimensions,
                embedding_provider_config=EmbeddingProviderConfig(
                    mode=PRODUCTION_EMBEDDING_MODE,
                    backend=backend_id,
                    dimensions=dimensions,
                    allow_fallback=False,
                ),
            )
        except Exception as exc:
            backend_results.append(
                BenchmarkBackendResult(
                    backend_id=backend_id,
                    provider_name=backend_id,
                    status="error",
                    metrics={},
                    query_results=(),
                    error=f"{type(exc).__name__}: {exc}",
                    rank=None,
                )
            )
            continue

        query_results = tuple(
            _evaluate_query(
                store=store,
                query=query,
                max_top_k=max(resolved_top_ks),
            )
            for query in dataset.queries
        )
        metrics = _aggregate_metrics(query_results=query_results, top_ks=resolved_top_ks)
        backend_results.append(
            BenchmarkBackendResult(
                backend_id=backend_id,
                provider_name=store.embedding_provider.name,
                status="ok",
                metrics=metrics,
                query_results=query_results,
                rank=None,
            )
        )

    ranked = _rank_backend_results(backend_results)
    return RetrievalBenchmarkRunResult(
        schema_version=_METRICS_SCHEMA_VERSION,
        task_id=task_id,
        run_id=run_id,
        dataset=dataset,
        top_ks=resolved_top_ks,
        dimensions=dimensions,
        backend_results=tuple(ranked),
    )


def write_benchmark_artifacts(
    *,
    result: RetrievalBenchmarkRunResult,
    output_dir: str | Path,
) -> BenchmarkArtifactPaths:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    dataset_path = root / "retrieval-benchmark-dataset.json"
    metrics_path = root / "retrieval-benchmark-metrics.json"
    report_path = root / "retrieval-benchmark-report.md"

    dataset_path.write_text(
        json.dumps(result.dataset.to_payload(), ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    metrics_path.write_text(
        json.dumps(result.to_payload(), ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        _render_markdown_report(
            result=result,
            dataset_path=dataset_path,
            metrics_path=metrics_path,
        ),
        encoding="utf-8",
    )

    return BenchmarkArtifactPaths(
        dataset_path=dataset_path,
        metrics_path=metrics_path,
        report_path=report_path,
    )


def _parse_dataset(payload: Mapping[str, Any]) -> BenchmarkDataset:
    schema_version = _expect_non_empty_str(payload.get("schema_version"), name="schema_version")
    if schema_version != _DATASET_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported dataset schema_version: expected {_DATASET_SCHEMA_VERSION}, got {schema_version}"
        )

    dataset_id = _expect_non_empty_str(payload.get("dataset_id"), name="dataset_id")
    description = _expect_non_empty_str(payload.get("description"), name="description")
    top_ks = _normalize_top_ks(payload.get("top_ks") or _DEFAULT_TOP_KS)

    raw_chunks = payload.get("chunks")
    if not isinstance(raw_chunks, list):
        raise ValueError("chunks must be a list")
    chunks: list[BenchmarkChunk] = []
    seen_chunk_ids: set[str] = set()
    for index, entry in enumerate(raw_chunks):
        if not isinstance(entry, Mapping):
            raise ValueError(f"chunks[{index}] must be an object")
        chunk_id = _expect_non_empty_str(entry.get("chunk_id"), name=f"chunks[{index}].chunk_id")
        if chunk_id in seen_chunk_ids:
            raise ValueError(f"duplicate chunk_id: {chunk_id}")
        seen_chunk_ids.add(chunk_id)
        chunks.append(
            BenchmarkChunk(
                chunk_id=chunk_id,
                text=_expect_non_empty_str(entry.get("text"), name=f"chunks[{index}].text"),
                source_path=_expect_non_empty_str(
                    entry.get("source_path"),
                    name=f"chunks[{index}].source_path",
                ),
                source_type=_expect_non_empty_str(
                    entry.get("source_type"),
                    name=f"chunks[{index}].source_type",
                ),
                task_id=_normalize_optional_str(entry.get("task_id")),
                run_id=_normalize_optional_str(entry.get("run_id")),
            )
        )
    if not chunks:
        raise ValueError("dataset must contain at least one chunk")

    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list):
        raise ValueError("queries must be a list")
    if len(raw_queries) < 10 or len(raw_queries) > 20:
        raise ValueError("dataset query count must be within [10, 20]")

    queries: list[BenchmarkQuery] = []
    seen_query_ids: set[str] = set()
    chunk_id_set = {chunk.chunk_id for chunk in chunks}
    for index, entry in enumerate(raw_queries):
        if not isinstance(entry, Mapping):
            raise ValueError(f"queries[{index}] must be an object")
        query_id = _expect_non_empty_str(entry.get("query_id"), name=f"queries[{index}].query_id")
        if query_id in seen_query_ids:
            raise ValueError(f"duplicate query_id: {query_id}")
        seen_query_ids.add(query_id)

        relevant_raw = entry.get("relevant_chunk_ids")
        if not isinstance(relevant_raw, list) or not relevant_raw:
            raise ValueError(f"queries[{index}].relevant_chunk_ids must be a non-empty list")

        relevant_chunk_ids: list[str] = []
        for rel_index, chunk_id in enumerate(relevant_raw):
            normalized = _expect_non_empty_str(
                chunk_id,
                name=f"queries[{index}].relevant_chunk_ids[{rel_index}]",
            )
            if normalized not in chunk_id_set:
                raise ValueError(
                    f"queries[{index}] references unknown chunk id: {normalized}"
                )
            relevant_chunk_ids.append(normalized)

        queries.append(
            BenchmarkQuery(
                query_id=query_id,
                query=_expect_non_empty_str(entry.get("query"), name=f"queries[{index}].query"),
                relevant_chunk_ids=tuple(relevant_chunk_ids),
            )
        )

    return BenchmarkDataset(
        schema_version=schema_version,
        dataset_id=dataset_id,
        description=description,
        top_ks=top_ks,
        chunks=tuple(chunks),
        queries=tuple(queries),
    )


def _to_index_chunks(chunks: Sequence[BenchmarkChunk]) -> list[ChunkForIndex]:
    return [
        ChunkForIndex(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            source_path=chunk.source_path,
            source_type=chunk.source_type,
            task_id=chunk.task_id,
            run_id=chunk.run_id,
            chunk_index=0,
            total_chunks=1,
        )
        for chunk in chunks
    ]


def _evaluate_query(
    *,
    store: EmbeddingIndexStore,
    query: BenchmarkQuery,
    max_top_k: int,
) -> QueryBenchmarkResult:
    hits = store.search(query.query, top_k=max_top_k)
    ranked_chunk_ids = tuple(hit.chunk_id for hit in hits)
    relevant = set(query.relevant_chunk_ids)
    first_relevant_rank: int | None = None
    for index, chunk_id in enumerate(ranked_chunk_ids):
        if chunk_id in relevant:
            first_relevant_rank = index + 1
            break
    return QueryBenchmarkResult(
        query_id=query.query_id,
        query=query.query,
        relevant_chunk_ids=query.relevant_chunk_ids,
        retrieved_chunk_ids=ranked_chunk_ids,
        first_relevant_rank=first_relevant_rank,
    )


def _aggregate_metrics(
    *,
    query_results: Sequence[QueryBenchmarkResult],
    top_ks: Sequence[int],
) -> dict[str, float]:
    if not query_results:
        return {}
    query_count = float(len(query_results))

    metrics: dict[str, float] = {}
    for k in top_ks:
        hit_sum = 0.0
        precision_sum = 0.0
        recall_sum = 0.0
        reciprocal_rank_sum = 0.0
        ndcg_sum = 0.0

        for result in query_results:
            relevant = set(result.relevant_chunk_ids)
            retrieved_top_k = result.retrieved_chunk_ids[:k]
            relevant_count = sum(1 for chunk_id in retrieved_top_k if chunk_id in relevant)

            hit_sum += 1.0 if relevant_count > 0 else 0.0
            precision_sum += float(relevant_count) / float(k)
            recall_sum += float(relevant_count) / float(len(relevant))
            if result.first_relevant_rank is not None and result.first_relevant_rank <= k:
                reciprocal_rank_sum += 1.0 / float(result.first_relevant_rank)
            ndcg_sum += _ndcg_at_k(
                retrieved_chunk_ids=retrieved_top_k,
                relevant_chunk_ids=relevant,
                k=k,
            )

        metrics[f"hit_rate_at_{k}"] = round(hit_sum / query_count, 6)
        metrics[f"precision_at_{k}"] = round(precision_sum / query_count, 6)
        metrics[f"recall_at_{k}"] = round(recall_sum / query_count, 6)
        metrics[f"mrr_at_{k}"] = round(reciprocal_rank_sum / query_count, 6)
        metrics[f"ndcg_at_{k}"] = round(ndcg_sum / query_count, 6)

    return metrics


def _ndcg_at_k(
    *,
    retrieved_chunk_ids: Sequence[str],
    relevant_chunk_ids: set[str],
    k: int,
) -> float:
    if not relevant_chunk_ids:
        return 0.0
    dcg = 0.0
    for index, chunk_id in enumerate(retrieved_chunk_ids[:k]):
        if chunk_id in relevant_chunk_ids:
            dcg += 1.0 / math.log2(float(index + 2))

    ideal_hits = min(len(relevant_chunk_ids), k)
    if ideal_hits <= 0:
        return 0.0
    idcg = sum(1.0 / math.log2(float(index + 2)) for index in range(ideal_hits))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def _rank_backend_results(
    backend_results: Sequence[BenchmarkBackendResult],
) -> list[BenchmarkBackendResult]:
    ranked = list(backend_results)
    scored_indexes = [
        index
        for index, result in enumerate(ranked)
        if result.status == "ok"
    ]
    scored_indexes.sort(
        key=lambda index: (
            -ranked[index].metrics.get("ndcg_at_3", -1.0),
            -ranked[index].metrics.get("mrr_at_3", -1.0),
            -ranked[index].metrics.get("hit_rate_at_3", -1.0),
            ranked[index].backend_id,
        )
    )
    for rank, index in enumerate(scored_indexes, start=1):
        ranked[index] = replace(ranked[index], rank=rank)
    return ranked


def _render_markdown_report(
    *,
    result: RetrievalBenchmarkRunResult,
    dataset_path: Path,
    metrics_path: Path,
) -> str:
    lines = [
        "# DKT-061 Retrieval Benchmark Report",
        "",
        f"- Task: `{result.task_id}`",
        f"- Run: `{result.run_id}`",
        f"- Dataset: `{result.dataset.dataset_id}`",
        f"- Query count: `{len(result.dataset.queries)}`",
        f"- Chunk count: `{len(result.dataset.chunks)}`",
        f"- Top-k thresholds: `{', '.join(str(value) for value in result.top_ks)}`",
        "",
        "## Evidence Pointers",
        f"- EVIDENCE:retrieval-benchmark-dataset@{dataset_path.as_posix()}",
        f"- EVIDENCE:retrieval-benchmark-metrics@{metrics_path.as_posix()}",
        "",
        "## Backend Summary",
        "| Rank | Backend | Provider | Status | hit@1 | hit@3 | mrr@3 | ndcg@3 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for backend in result.backend_results:
        if backend.status != "ok":
            lines.append(
                "| - | `{backend}` | `{provider}` | error | n/a | n/a | n/a | n/a |".format(
                    backend=backend.backend_id,
                    provider=backend.provider_name,
                )
            )
            if backend.error:
                lines.append(f"- Error `{backend.backend_id}`: `{backend.error}`")
            continue
        lines.append(
            "| {rank} | `{backend}` | `{provider}` | ok | {hit1:.4f} | {hit3:.4f} | {mrr3:.4f} | {ndcg3:.4f} |".format(
                rank=backend.rank if backend.rank is not None else "-",
                backend=backend.backend_id,
                provider=backend.provider_name,
                hit1=backend.metrics.get("hit_rate_at_1", 0.0),
                hit3=backend.metrics.get("hit_rate_at_3", 0.0),
                mrr3=backend.metrics.get("mrr_at_3", 0.0),
                ndcg3=backend.metrics.get("ndcg_at_3", 0.0),
            )
        )

    lines.extend(
        [
            "",
            "## Decision Support Notes",
            "- Primary ranking key: `ndcg_at_3`.",
            "- Tie-breakers: `mrr_at_3`, then `hit_rate_at_3`, then backend id.",
            "- Use this report and metrics JSON as inputs to DKT-062 default-model selection.",
            "",
        ]
    )
    return "\n".join(lines)


def _expect_non_empty_str(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    return normalized


def _normalize_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional string value must be a string or null")
    normalized = value.strip()
    return normalized if normalized else None


def _normalize_top_ks(values: Sequence[int] | Any) -> tuple[int, ...]:
    if not isinstance(values, Sequence):
        raise ValueError("top_ks must be a sequence")

    normalized: list[int] = []
    for value in values:
        if isinstance(value, bool):
            raise ValueError("top_k entries must be integers > 0")
        if not isinstance(value, int):
            raise ValueError("top_k entries must be integers > 0")
        if value <= 0:
            raise ValueError("top_k entries must be integers > 0")
        normalized.append(int(value))
    if not normalized:
        return ()
    return tuple(sorted(set(normalized)))
