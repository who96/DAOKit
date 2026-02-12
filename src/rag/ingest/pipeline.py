from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rag.ingest.chunker import ChunkInput, ChunkRecord, IngestionError, chunk_document
from rag.index.store import ChunkForIndex, EmbeddingIndexStore


@dataclass(frozen=True)
class FileIngestionItem:
    path: str | Path
    source_type: str | None = None
    task_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class RebuildResult:
    source_count: int
    chunk_count: int
    index_path: Path


def rebuild_index(
    items: Iterable[FileIngestionItem],
    *,
    index_path: str | Path,
    chunk_size: int = 480,
    chunk_overlap: int = 64,
    dimensions: int = 64,
) -> RebuildResult:
    """
    Build the RAG index deterministically.

    Deterministic rebuild contract:
    1. Normalize source list and sort by lineage + file path.
    2. Canonicalize source text by type (markdown/json/log) before chunking.
    3. Generate stable chunk ids from source id + chunk index + chunk text.
    4. Sort all chunks by lineage/path/order before embedding.
    5. Persist index JSON with stable key ordering.
    """

    normalized_items = sorted(
        [_normalize_item(item) for item in items],
        key=lambda item: (
            item.task_id or "",
            item.run_id or "",
            item.source_type,
            item.path.as_posix(),
        ),
    )

    all_chunks: list[ChunkRecord] = []
    for item in normalized_items:
        raw_text = item.path.read_text(encoding="utf-8")
        payload = ChunkInput(
            source_id=item.path.as_posix(),
            source_path=item.path.as_posix(),
            source_type=item.source_type,
            text=raw_text,
            task_id=item.task_id,
            run_id=item.run_id,
        )
        all_chunks.extend(
            chunk_document(
                payload,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        )

    sorted_chunks = sorted(
        all_chunks,
        key=lambda chunk: (
            chunk.task_id or "",
            chunk.run_id or "",
            chunk.source_type,
            chunk.source_path,
            chunk.chunk_index,
            chunk.chunk_id,
        ),
    )
    index_chunks = [
        ChunkForIndex(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            source_path=chunk.source_path,
            source_type=chunk.source_type,
            task_id=chunk.task_id,
            run_id=chunk.run_id,
            chunk_index=chunk.chunk_index,
            total_chunks=chunk.total_chunks,
        )
        for chunk in sorted_chunks
    ]
    store = EmbeddingIndexStore.from_chunks(index_chunks, dimensions=dimensions)
    written_path = store.save(index_path)
    return RebuildResult(
        source_count=len(normalized_items),
        chunk_count=len(index_chunks),
        index_path=written_path,
    )


@dataclass(frozen=True)
class _NormalizedItem:
    path: Path
    source_type: str
    task_id: str | None
    run_id: str | None


def _normalize_item(item: FileIngestionItem) -> _NormalizedItem:
    path = Path(item.path).expanduser()
    if not path.is_file():
        raise IngestionError(f"ingestion source does not exist: {path}")
    source_type = item.source_type.strip().lower() if item.source_type else _infer_source_type(path)
    if source_type not in {"markdown", "json", "log"}:
        raise IngestionError("source_type must be markdown/json/log")
    task_id = _normalize_optional_identifier(item.task_id)
    run_id = _normalize_optional_identifier(item.run_id)
    return _NormalizedItem(path=path, source_type=source_type, task_id=task_id, run_id=run_id)


def _infer_source_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".json":
        return "json"
    if suffix in {".log", ".txt"}:
        return "log"
    raise IngestionError(f"cannot infer source_type for {path}; provide source_type explicitly")


def _normalize_optional_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None
