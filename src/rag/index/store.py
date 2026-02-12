from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from rag.index.embeddings import cosine_similarity, embed_text


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
    """Deterministic in-memory embedding index with JSON persistence."""

    def __init__(
        self,
        *,
        dimensions: int = 64,
        chunks: Iterable[_IndexedChunk] | None = None,
    ) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be > 0")
        self.dimensions = int(dimensions)
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
    ) -> "EmbeddingIndexStore":
        indexed = [
            _IndexedChunk(
                payload=chunk,
                embedding=embed_text(chunk.text, dimensions=dimensions),
            )
            for chunk in chunks
        ]
        return cls(dimensions=dimensions, chunks=indexed)

    @classmethod
    def load(cls, path: str | Path) -> "EmbeddingIndexStore":
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        dimensions = int(doc["dimensions"])
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
            embedding_raw = entry.get("embedding")
            if not isinstance(embedding_raw, list):
                raise ValueError("embedding must be a list")
            embedding = tuple(float(value) for value in embedding_raw)
            indexed.append(_IndexedChunk(payload=payload, embedding=embedding))
        return cls(dimensions=dimensions, chunks=indexed)

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "rag-index.v1",
            "dimensions": self.dimensions,
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

        query_embedding = embed_text(normalized_query, dimensions=self.dimensions)
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
