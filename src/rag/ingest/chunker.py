from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable


SUPPORTED_SOURCE_TYPES = ("markdown", "json", "log")


class IngestionError(RuntimeError):
    """Raised when ingestion payloads are malformed or unsupported."""


@dataclass(frozen=True)
class ChunkInput:
    source_id: str
    source_path: str
    source_type: str
    text: str
    task_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    text: str
    source_id: str
    source_path: str
    source_type: str
    task_id: str | None
    run_id: str | None
    chunk_index: int
    total_chunks: int


def normalize_source_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_SOURCE_TYPES:
        raise IngestionError(
            f"unsupported source_type {value!r}; expected one of {SUPPORTED_SOURCE_TYPES!r}"
        )
    return normalized


def chunk_document(
    payload: ChunkInput,
    *,
    chunk_size: int = 480,
    chunk_overlap: int = 64,
) -> list[ChunkRecord]:
    if chunk_size <= 0:
        raise IngestionError("chunk_size must be > 0")
    if chunk_overlap < 0:
        raise IngestionError("chunk_overlap must be >= 0")
    if chunk_overlap >= chunk_size:
        raise IngestionError("chunk_overlap must be < chunk_size")

    source_type = normalize_source_type(payload.source_type)
    normalized_text = _normalize_text(payload.text, source_type=source_type)
    pieces = list(_split_text(normalized_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
    total = len(pieces)
    records: list[ChunkRecord] = []
    for index, text in enumerate(pieces):
        chunk_id = _stable_chunk_id(
            source_id=payload.source_id,
            chunk_index=index,
            text=text,
        )
        records.append(
            ChunkRecord(
                chunk_id=chunk_id,
                text=text,
                source_id=payload.source_id,
                source_path=payload.source_path,
                source_type=source_type,
                task_id=payload.task_id,
                run_id=payload.run_id,
                chunk_index=index,
                total_chunks=total,
            )
        )
    return records


def _normalize_text(text: str, *, source_type: str) -> str:
    if source_type == "json":
        parsed = json.loads(text)
        return json.dumps(parsed, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    if source_type == "markdown":
        return _normalize_markdown(text)
    if source_type == "log":
        return _normalize_log(text)
    raise IngestionError(f"unsupported source_type {source_type!r}")


def _normalize_markdown(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    compacted: list[str] = []
    last_blank = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if not last_blank:
                compacted.append("")
            last_blank = True
            continue
        compacted.append(line)
        last_blank = False
    return "\n".join(compacted).strip()


def _normalize_log(text: str) -> str:
    normalized_lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(normalized_lines).strip()


def _split_text(text: str, *, chunk_size: int, chunk_overlap: int) -> Iterable[str]:
    normalized = text.strip()
    if not normalized:
        return []

    chunks: list[str] = []
    length = len(normalized)
    cursor = 0
    while cursor < length:
        ideal_end = min(length, cursor + chunk_size)
        end = _choose_breakpoint(normalized, start=cursor, ideal_end=ideal_end, chunk_size=chunk_size)
        if end <= cursor:
            end = ideal_end
        piece = normalized[cursor:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        next_cursor = end - chunk_overlap
        if next_cursor <= cursor:
            next_cursor = end
        cursor = next_cursor
    return chunks


def _choose_breakpoint(text: str, *, start: int, ideal_end: int, chunk_size: int) -> int:
    if ideal_end >= len(text):
        return ideal_end
    scan_floor = start + max(1, int(chunk_size * 0.6))
    scan_floor = min(scan_floor, ideal_end)
    newline = text.rfind("\n", scan_floor, ideal_end + 1)
    if newline > start:
        return newline
    whitespace = text.rfind(" ", scan_floor, ideal_end + 1)
    if whitespace > start:
        return whitespace
    return ideal_end


def _stable_chunk_id(*, source_id: str, chunk_index: int, text: str) -> str:
    canonical = f"{source_id}|{chunk_index}|{text}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
