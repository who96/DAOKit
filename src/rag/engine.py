from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

import chromadb

_SENTENCE_TRANSFORMER_EF_AVAILABLE = True
try:
    from chromadb.utils.embedding_functions import (
        SentenceTransformerEmbeddingFunction,
    )
except ImportError:
    _SENTENCE_TRANSFORMER_EF_AVAILABLE = False


class RAGEngine:
    """Chroma-backed RAG engine with semantic search."""

    def __init__(
        self,
        collection_name: str,
        persist_dir: str = "./chroma_db",
        embedding_model: str = "BAAI/bge-small-zh-v1.5",
        *,
        embedding_function: Any | None = None,
    ) -> None:
        self._collection_name = collection_name
        self._persist_dir = persist_dir
        self._embedding_model = embedding_model
        self._client = chromadb.PersistentClient(path=persist_dir)

        ef = embedding_function or _build_embedding_function(embedding_model)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> int:
        """Add documents to the collection. Returns the count added."""
        if not texts:
            return 0
        if metadatas is not None and len(metadatas) != len(texts):
            msg = (
                f"metadatas length ({len(metadatas)}) "
                f"!= texts length ({len(texts)})"
            )
            raise ValueError(msg)

        ids = _generate_ids(texts)
        kwargs: dict[str, Any] = {"documents": texts, "ids": ids}
        if metadatas is not None:
            kwargs["metadatas"] = metadatas
        self._collection.upsert(**kwargs)
        return len(texts)

    def add_file(
        self,
        file_path: str | Path,
        *,
        chunk_size: int = 480,
        chunk_overlap: int = 64,
    ) -> int:
        """Read a text file, split into chunks, and add to the collection."""
        path = Path(file_path)
        text = path.read_text(encoding="utf-8")
        chunks = split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        metadatas = [
            {"source": str(path), "chunk_index": i} for i in range(len(chunks))
        ]
        return self.add_documents(chunks, metadatas=metadatas)

    def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic search. Returns ``[{text, score, metadata}, ...]``."""
        count = self._collection.count()
        if count == 0:
            return []
        effective_k = min(top_k, count)

        results = self._collection.query(
            query_texts=[query_text],
            n_results=effective_k,
            include=["documents", "distances", "metadatas"],
        )

        documents = (results.get("documents") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]

        hits: list[dict[str, Any]] = []
        for doc, dist, meta in zip(documents, distances, metadatas):
            hits.append({
                "text": doc,
                "score": round(1.0 - dist, 6),
                "metadata": meta or {},
            })
        return hits

    def delete_collection(self) -> None:
        """Delete the current collection from the database."""
        self._client.delete_collection(name=self._collection_name)

    @staticmethod
    def list_collections(persist_dir: str = "./chroma_db") -> list[str]:
        """List all collection names in *persist_dir*."""
        client = chromadb.PersistentClient(path=persist_dir)
        return [c.name for c in client.list_collections()]

    @property
    def count(self) -> int:
        """Number of documents stored in the collection."""
        return self._collection.count()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"RAGEngine(collection={self._collection_name!r}, "
            f"persist_dir={self._persist_dir!r}, "
            f"model={self._embedding_model!r})"
        )


# ------------------------------------------------------------------
# Module-private helpers
# ------------------------------------------------------------------


def _build_embedding_function(
    model_name: str | None,
) -> SentenceTransformerEmbeddingFunction | None:
    if model_name is None:
        return None
    if not _SENTENCE_TRANSFORMER_EF_AVAILABLE:
        return None
    return SentenceTransformerEmbeddingFunction(model_name=model_name)


def _generate_ids(texts: list[str]) -> list[str]:
    batch_salt = str(time.monotonic_ns())
    return [
        "doc-"
        + hashlib.sha256(f"{batch_salt}:{i}:{t}".encode()).hexdigest()[:16]
        for i, t in enumerate(texts)
    ]


def split_text(
    text: str,
    *,
    chunk_size: int = 480,
    chunk_overlap: int = 64,
) -> list[str]:
    """Split *text* into overlapping chunks by character count."""
    if chunk_size <= 0:
        msg = f"chunk_size must be positive, got {chunk_size}"
        raise ValueError(msg)
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        msg = f"chunk_overlap must be in [0, chunk_size), got {chunk_overlap}"
        raise ValueError(msg)
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    step = chunk_size - chunk_overlap
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks
