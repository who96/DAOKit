from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from rag.index.embeddings import embed_text
from rag.index.providers import DETERMINISTIC_FIXTURE_BACKEND, TEST_EMBEDDING_MODE
from rag.index.store import EmbeddingIndexStore


def _legacy_payload(*, text: str, dimensions: int) -> dict[str, object]:
    return {
        "schema_version": "rag-index.v1",
        "dimensions": dimensions,
        "chunk_count": 1,
        "chunks": [
            {
                "chunk_id": "legacy-1",
                "text": text,
                "source_path": "docs/legacy.md",
                "source_type": "markdown",
                "task_id": "DKT-011",
                "run_id": "RUN-LEGACY",
                "chunk_index": 0,
                "total_chunks": 1,
                "embedding": list(embed_text(text, dimensions=dimensions)),
            }
        ],
    }


class EmbeddingMigrationCompatibilityTests(unittest.TestCase):
    def test_load_legacy_payload_without_provider_metadata_defaults_to_test_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy-index.json"
            path.write_text(
                json.dumps(_legacy_payload(text="legacy deterministic payload", dimensions=16)),
                encoding="utf-8",
            )

            store = EmbeddingIndexStore.load(path)
            self.assertEqual(store.embedding_provider.mode, TEST_EMBEDDING_MODE)
            self.assertEqual(store.embedding_provider.name, DETERMINISTIC_FIXTURE_BACKEND)

            hits = store.search("legacy deterministic payload", top_k=1)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].chunk_id, "legacy-1")

    def test_load_payload_with_legacy_backend_name_without_mode_keeps_fixture_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _legacy_payload(text="legacy backend compatibility", dimensions=12)
            payload["embedding_provider"] = {"backend": DETERMINISTIC_FIXTURE_BACKEND}

            path = Path(tmp) / "legacy-provider-index.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            store = EmbeddingIndexStore.load(path)
            self.assertEqual(store.embedding_provider.mode, TEST_EMBEDDING_MODE)
            self.assertEqual(store.embedding_provider.name, DETERMINISTIC_FIXTURE_BACKEND)

            hits = store.search("legacy backend compatibility", top_k=1)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].chunk_id, "legacy-1")


if __name__ == "__main__":
    unittest.main()
