from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rag.evaluation.benchmark import (
    DEFAULT_DATASET_PATH,
    load_benchmark_dataset,
    run_retrieval_benchmark,
    write_benchmark_artifacts,
)
from rag.index.providers import (
    LOCAL_CHAR_TRIGRAM_BACKEND,
    LOCAL_TOKEN_SIGNATURE_BACKEND,
)


class RetrievalBenchmarkTests(unittest.TestCase):
    def test_default_dataset_is_representative_and_valid(self) -> None:
        dataset = load_benchmark_dataset(DEFAULT_DATASET_PATH)
        self.assertGreaterEqual(len(dataset.queries), 10)
        self.assertLessEqual(len(dataset.queries), 20)

        chunk_ids = {chunk.chunk_id for chunk in dataset.chunks}
        self.assertGreaterEqual(len(chunk_ids), 10)

        for query in dataset.queries:
            self.assertGreaterEqual(len(query.relevant_chunk_ids), 1)
            self.assertTrue(set(query.relevant_chunk_ids).issubset(chunk_ids))

    def test_benchmark_outputs_top_k_quality_metrics_per_backend(self) -> None:
        dataset = load_benchmark_dataset(DEFAULT_DATASET_PATH)
        result = run_retrieval_benchmark(
            dataset=dataset,
            backend_ids=[
                LOCAL_TOKEN_SIGNATURE_BACKEND,
                LOCAL_CHAR_TRIGRAM_BACKEND,
            ],
            top_ks=(1, 3, 5),
            dimensions=64,
        )

        self.assertEqual(len(result.backend_results), 2)
        for backend in result.backend_results:
            self.assertIn("hit_rate_at_1", backend.metrics)
            self.assertIn("hit_rate_at_3", backend.metrics)
            self.assertIn("mrr_at_3", backend.metrics)
            self.assertIn("ndcg_at_3", backend.metrics)

    def test_artifact_layout_is_stable_and_evidence_linked(self) -> None:
        dataset = load_benchmark_dataset(DEFAULT_DATASET_PATH)
        result = run_retrieval_benchmark(
            dataset=dataset,
            backend_ids=[
                LOCAL_TOKEN_SIGNATURE_BACKEND,
                LOCAL_CHAR_TRIGRAM_BACKEND,
            ],
            top_ks=(1, 3, 5),
            dimensions=64,
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            paths = write_benchmark_artifacts(
                result=result,
                output_dir=output_dir,
            )
            self.assertTrue(paths.dataset_path.is_file())
            self.assertTrue(paths.metrics_path.is_file())
            self.assertTrue(paths.report_path.is_file())

            report = paths.report_path.read_text(encoding="utf-8")
            self.assertIn("EVIDENCE:retrieval-benchmark-dataset@", report)
            self.assertIn("EVIDENCE:retrieval-benchmark-metrics@", report)


if __name__ == "__main__":
    unittest.main()
