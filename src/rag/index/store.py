from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from rag.index.embeddings import cosine_similarity
from rag.index.providers import (
    DETERMINISTIC_FIXTURE_BACKEND,
    EmbeddingProvider,
    EmbeddingProviderConfig,
    PRODUCTION_EMBEDDING_MODE,
    TEST_EMBEDDING_MODE,
    build_embedding_provider,
)


def _expect_non_empty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be a non-empty string")
    return normalized


def _normalize_optional_string(value: Any, *, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string or null")
    stripped = value.strip()
    return stripped if stripped else None


@dataclass(frozen=True)
class ChunkForIndex:
    chunk_id: str
    text: str
    source_path: str
    source_type: str
    task_id: str | None
    run_id: str | None
    chunk_index: int
    total_chunks: int


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    source_path: str
    source_type: str
    task_id: str | None
    run_id: str | None
    score: float
    text: str
    chunk_index: int
    total_chunks: int


@dataclass(frozen=True)
class _IndexedChunk:
    payload: ChunkForIndex
    embedding: tuple[float, ...]


class EmbeddingIndexStore:
    """Embedding index with pluggable providers and JSON persistence."""

    def __init__(
        self,
        *,
        dimensions: int = 64,
        chunks: Iterable[_IndexedChunk] | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_provider_config: EmbeddingProviderConfig | None = None,
    ) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be > 0")
        self.dimensions = int(dimensions)
        self.embedding_provider = _resolve_embedding_provider(
            dimensions=self.dimensions,
            embedding_provider=embedding_provider,
            embedding_provider_config=embedding_provider_config,
            default_mode=PRODUCTION_EMBEDDING_MODE,
        )
        self._chunks = sorted(
            list(chunks or []),
            key=lambda item: (
                item.payload.task_id or "",
                item.payload.run_id or "",
                item.payload.source_type,
                item.payload.source_path,
                item.payload.chunk_index,
                item.payload.chunk_id,
            ),
        )

    @classmethod
    def from_chunks(
        cls,
        chunks: Iterable[ChunkForIndex],
        *,
        dimensions: int = 64,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_provider_config: EmbeddingProviderConfig | None = None,
    ) -> "EmbeddingIndexStore":
        chunk_list = list(chunks)
        provider = _resolve_embedding_provider(
            dimensions=dimensions,
            embedding_provider=embedding_provider,
            embedding_provider_config=embedding_provider_config,
            default_mode=PRODUCTION_EMBEDDING_MODE,
        )
        vectors = provider.embed_texts([chunk.text for chunk in chunk_list])
        if len(vectors) != len(chunk_list):
            raise ValueError("embedding provider returned inconsistent vector count")

        indexed = [
            _IndexedChunk(
                payload=chunk,
                embedding=_coerce_embedding_vector(
                    vectors[index],
                    dimensions=dimensions,
                    name=f"chunk[{index}]",
                ),
            )
            for index, chunk in enumerate(chunk_list)
        ]
        return cls(
            dimensions=dimensions,
            chunks=indexed,
            embedding_provider=provider,
        )

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_provider_config: EmbeddingProviderConfig | None = None,
    ) -> "EmbeddingIndexStore":
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        dimensions = int(doc["dimensions"])

        inferred_config = embedding_provider_config
        if embedding_provider is None and inferred_config is None:
            inferred_config = _provider_config_from_payload(
                doc.get("embedding_provider"),
                dimensions=dimensions,
            )
        provider = _resolve_embedding_provider(
            dimensions=dimensions,
            embedding_provider=embedding_provider,
            embedding_provider_config=inferred_config,
            default_mode=TEST_EMBEDDING_MODE,
        )

        raw_chunks = doc.get("chunks")
        if not isinstance(raw_chunks, list):
            raise ValueError("index payload missing chunks list")

        indexed: list[_IndexedChunk] = []
        for entry in raw_chunks:
            if not isinstance(entry, Mapping):
                raise ValueError("chunk entry must be an object")
            payload = ChunkForIndex(
                chunk_id=_expect_non_empty_string(entry.get("chunk_id"), name="chunk_id"),
                text=_expect_non_empty_string(entry.get("text"), name="text"),
                source_path=_expect_non_empty_string(entry.get("source_path"), name="source_path"),
                source_type=_expect_non_empty_string(entry.get("source_type"), name="source_type"),
                task_id=_normalize_optional_string(entry.get("task_id"), name="task_id"),
                run_id=_normalize_optional_string(entry.get("run_id"), name="run_id"),
                chunk_index=int(entry.get("chunk_index", 0)),
                total_chunks=int(entry.get("total_chunks", 0)),
            )
            embedding = _coerce_embedding_vector(
                entry.get("embedding"),
                dimensions=dimensions,
                name="embedding",
            )
            indexed.append(_IndexedChunk(payload=payload, embedding=embedding))
        return cls(
            dimensions=dimensions,
            chunks=indexed,
            embedding_provider=provider,
        )

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "rag-index.v1",
            "dimensions": self.dimensions,
            "embedding_provider": {
                "mode": self.embedding_provider.mode,
                "backend": self.embedding_provider.name,
                "name": self.embedding_provider.name,
                "deterministic": bool(self.embedding_provider.deterministic),
            },
            "chunk_count": len(self._chunks),
            "chunks": [
                {
                    "chunk_id": entry.payload.chunk_id,
                    "text": entry.payload.text,
                    "source_path": entry.payload.source_path,
                    "source_type": entry.payload.source_type,
                    "task_id": entry.payload.task_id,
                    "run_id": entry.payload.run_id,
                    "chunk_index": entry.payload.chunk_index,
                    "total_chunks": entry.payload.total_chunks,
                    "embedding": list(entry.embedding),
                }
                for entry in self._chunks
            ],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        target.write_text(encoded + "\n", encoding="utf-8")
        return target

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        task_id: str | None = None,
        run_id: str | None = None,
        source_type: str | None = None,
    ) -> list[SearchHit]:
        normalized_query = _expect_non_empty_string(query, name="query")
        if top_k <= 0:
            return []

        query_vectors = self.embedding_provider.embed_texts([normalized_query])
        if len(query_vectors) != 1:
            raise ValueError("embedding provider must return exactly one query vector")
        query_embedding = _coerce_embedding_vector(
            query_vectors[0],
            dimensions=self.dimensions,
            name="query_embedding",
        )

        matches: list[SearchHit] = []
        for entry in self._chunks:
            payload = entry.payload
            if task_id is not None and payload.task_id != task_id:
                continue
            if run_id is not None and payload.run_id != run_id:
                continue
            if source_type is not None and payload.source_type != source_type:
                continue

            score = cosine_similarity(query_embedding, entry.embedding)
            matches.append(
                SearchHit(
                    chunk_id=payload.chunk_id,
                    source_path=payload.source_path,
                    source_type=payload.source_type,
                    task_id=payload.task_id,
                    run_id=payload.run_id,
                    score=score,
                    text=payload.text,
                    chunk_index=payload.chunk_index,
                    total_chunks=payload.total_chunks,
                )
            )

        matches.sort(key=lambda hit: (-hit.score, hit.chunk_id))
        return matches[:top_k]


def _provider_config_from_payload(
    payload: Any,
    *,
    dimensions: int,
) -> EmbeddingProviderConfig:
    if not isinstance(payload, Mapping):
        return EmbeddingProviderConfig(mode=TEST_EMBEDDING_MODE, dimensions=dimensions)

    raw_mode = payload.get("mode")
    mode = TEST_EMBEDDING_MODE
    if isinstance(raw_mode, str) and raw_mode.strip().lower() in {
        TEST_EMBEDDING_MODE,
        PRODUCTION_EMBEDDING_MODE,
    }:
        mode = raw_mode.strip().lower()

    raw_backend = payload.get("backend")
    backend: str | None = None
    if isinstance(raw_backend, str) and raw_backend.strip():
        backend = raw_backend.strip().lower()
    else:
        raw_name = payload.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            backend = raw_name.strip().lower()

    # Compatibility guard: deterministic fixture backend is a test-only contract,
    # including for legacy payloads that omitted/serialized mode incorrectly.
    if backend == DETERMINISTIC_FIXTURE_BACKEND:
        mode = TEST_EMBEDDING_MODE

    raw_allow_fallback = payload.get("allow_fallback")
    allow_fallback = True
    if isinstance(raw_allow_fallback, bool):
        allow_fallback = raw_allow_fallback

    raw_model = payload.get("openai_model")
    openai_model = "text-embedding-3-small"
    if isinstance(raw_model, str) and raw_model.strip():
        openai_model = raw_model.strip()

    return EmbeddingProviderConfig(
        mode=mode,
        backend=backend,
        dimensions=dimensions,
        allow_fallback=allow_fallback,
        openai_model=openai_model,
    )


def _resolve_embedding_provider(
    *,
    dimensions: int,
    embedding_provider: EmbeddingProvider | None,
    embedding_provider_config: EmbeddingProviderConfig | None,
    default_mode: str,
) -> EmbeddingProvider:
    if embedding_provider is not None and embedding_provider_config is not None:
        raise ValueError("embedding_provider and embedding_provider_config are mutually exclusive")

    if embedding_provider is not None:
        if int(embedding_provider.dimensions) != int(dimensions):
            raise ValueError("embedding provider dimensions do not match store dimensions")
        return embedding_provider

    config = embedding_provider_config or EmbeddingProviderConfig(
        mode=default_mode,
        dimensions=dimensions,
    )
    if int(config.dimensions) != int(dimensions):
        config = replace(config, dimensions=dimensions)

    provider = build_embedding_provider(config)
    if int(provider.dimensions) != int(dimensions):
        raise ValueError("embedding provider dimensions do not match store dimensions")
    return provider


def _coerce_embedding_vector(
    value: Any,
    *,
    dimensions: int,
    name: str,
) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{name} must be a list of numbers")

    vector = tuple(float(item) for item in value)
    if len(vector) != dimensions:
        raise ValueError(f"{name} must contain exactly {dimensions} values")
    return vector
