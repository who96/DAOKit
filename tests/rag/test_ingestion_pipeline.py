from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from rag.ingest.pipeline import FileIngestionItem, rebuild_index
from rag.index.store import EmbeddingIndexStore


class RagIngestionPipelineTests(unittest.TestCase):
    def test_new_documents_are_indexed_and_searchable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_dir = root / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)

            markdown_path = docs_dir / "overview.md"
            markdown_path.write_text(
                "# DAOKit\n\nRAG ingestion builds a searchable memory layer.\n",
                encoding="utf-8",
            )

            json_path = docs_dir / "state.json"
            json_path.write_text(
                json.dumps({"task": "DKT-011", "status": "indexed"}, sort_keys=True),
                encoding="utf-8",
            )

            log_path = docs_dir / "run.log"
            log_path.write_text(
                "INFO retrieval pipeline ready\nINFO searchable index available\n",
                encoding="utf-8",
            )

            index_path = root / "rag-index.json"
            result = rebuild_index(
                [
                    FileIngestionItem(path=markdown_path, task_id="DKT-011", run_id="RUN-A"),
                    FileIngestionItem(path=json_path, task_id="DKT-011", run_id="RUN-A"),
                    FileIngestionItem(path=log_path, task_id="DKT-011", run_id="RUN-A"),
                ],
                index_path=index_path,
            )

            self.assertEqual(result.source_count, 3)
            self.assertTrue(index_path.is_file())

            store = EmbeddingIndexStore.load(index_path)
            hits = store.search("searchable memory index", top_k=5)

            self.assertGreaterEqual(len(hits), 1)
            self.assertEqual(hits[0].task_id, "DKT-011")
            self.assertEqual(hits[0].run_id, "RUN-A")
            self.assertIn(hits[0].source_type, {"markdown", "json", "log"})

    def test_retrieval_supports_task_and_run_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_dir = root / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)

            shared_text = "incident replay remains retrievable for debugging"
            first = docs_dir / "first.md"
            first.write_text(shared_text, encoding="utf-8")
            second = docs_dir / "second.md"
            second.write_text(shared_text, encoding="utf-8")

            index_path = root / "rag-index.json"
            rebuild_index(
                [
                    FileIngestionItem(path=first, task_id="DKT-011", run_id="RUN-1"),
                    FileIngestionItem(path=second, task_id="DKT-012", run_id="RUN-2"),
                ],
                index_path=index_path,
            )

            store = EmbeddingIndexStore.load(index_path)
            all_hits = store.search("incident replay retrievable", top_k=10)
            filtered_hits = store.search(
                "incident replay retrievable",
                top_k=10,
                task_id="DKT-012",
                run_id="RUN-2",
            )

            self.assertGreaterEqual(len(all_hits), 2)
            self.assertEqual(len(filtered_hits), 1)
            self.assertEqual(filtered_hits[0].task_id, "DKT-012")
            self.assertEqual(filtered_hits[0].run_id, "RUN-2")

    def test_index_rebuild_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_dir = root / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)

            a_path = docs_dir / "a.md"
            b_path = docs_dir / "b.log"
            c_path = docs_dir / "c.json"

            a_path.write_text("alpha beta gamma", encoding="utf-8")
            b_path.write_text("beta gamma delta\n", encoding="utf-8")
            c_path.write_text(
                json.dumps({"k1": "gamma", "k2": "delta"}, sort_keys=True),
                encoding="utf-8",
            )

            first_index = root / "index-first.json"
            second_index = root / "index-second.json"

            rebuild_index(
                [
                    FileIngestionItem(path=c_path, task_id="DKT-011", run_id="RUN-DET"),
                    FileIngestionItem(path=a_path, task_id="DKT-011", run_id="RUN-DET"),
                    FileIngestionItem(path=b_path, task_id="DKT-011", run_id="RUN-DET"),
                ],
                index_path=first_index,
            )
            rebuild_index(
                [
                    FileIngestionItem(path=b_path, task_id="DKT-011", run_id="RUN-DET"),
                    FileIngestionItem(path=c_path, task_id="DKT-011", run_id="RUN-DET"),
                    FileIngestionItem(path=a_path, task_id="DKT-011", run_id="RUN-DET"),
                ],
                index_path=second_index,
            )

            first_bytes = first_index.read_bytes()
            second_bytes = second_index.read_bytes()

            self.assertEqual(first_bytes, second_bytes)
            self.assertEqual(
                hashlib.sha256(first_bytes).hexdigest(),
                hashlib.sha256(second_bytes).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
