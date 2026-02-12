from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from rag.ingest.pipeline import FileIngestionItem, rebuild_index
from rag.retrieval import PolicyAwareRetriever, RetrievalPolicyConfig, policy_from_mapping


class RetrievalPolicyTests(unittest.TestCase):
    def _build_index(self, root: Path) -> Path:
        docs_dir = root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        planning = docs_dir / "planning.md"
        planning.write_text(
            "retrieval guidance for orchestrator planning with source attribution",
            encoding="utf-8",
        )
        troubleshooting = docs_dir / "troubleshooting.log"
        troubleshooting.write_text(
            "troubleshooting retrieval policy confidence threshold for failures",
            encoding="utf-8",
        )

        index_path = root / "rag-index.json"
        rebuild_index(
            [
                FileIngestionItem(path=planning, task_id="DKT-012", run_id="RUN-012"),
                FileIngestionItem(path=troubleshooting, task_id="DKT-012", run_id="RUN-012"),
            ],
            index_path=index_path,
        )
        return index_path

    def test_retrieval_includes_sources_and_relevance_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index_path = self._build_index(Path(tmp))
            retriever = PolicyAwareRetriever(index_path=index_path)

            result = retriever.retrieve(
                use_case="planning",
                query="orchestrator planning retrieval attribution",
                task_id="DKT-012",
                run_id="RUN-012",
                policy=RetrievalPolicyConfig(
                    enabled=True,
                    top_k=5,
                    min_relevance_score=-1.0,
                    allow_global_fallback=True,
                ),
            )

            self.assertTrue(result.enabled)
            self.assertGreaterEqual(len(result.sources), 1)
            first = result.sources[0]
            self.assertTrue(first.source_path)
            self.assertTrue(first.source_type)
            self.assertIsInstance(first.relevance_score, float)
            self.assertGreaterEqual(first.relevance_score, -1.0)

    def test_confidence_threshold_filters_low_relevance_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index_path = self._build_index(Path(tmp))
            retriever = PolicyAwareRetriever(index_path=index_path)

            broad = retriever.retrieve(
                use_case="troubleshooting",
                query="retrieval policy threshold",
                task_id="DKT-012",
                run_id="RUN-012",
                policy=RetrievalPolicyConfig(
                    enabled=True,
                    top_k=5,
                    min_relevance_score=-1.0,
                    allow_global_fallback=True,
                ),
            )

            self.assertGreaterEqual(len(broad.sources), 1)
            strict = retriever.retrieve(
                use_case="troubleshooting",
                query="retrieval policy threshold",
                task_id="DKT-012",
                run_id="RUN-012",
                policy=RetrievalPolicyConfig(
                    enabled=True,
                    top_k=5,
                    min_relevance_score=broad.sources[0].relevance_score + 1e-6,
                    allow_global_fallback=True,
                ),
            )
            self.assertEqual(strict.sources, ())

    def test_disabled_policy_returns_empty_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index_path = self._build_index(Path(tmp))
            retriever = PolicyAwareRetriever(index_path=index_path)

            result = retriever.retrieve(
                use_case="planning",
                query="orchestrator planning retrieval attribution",
                task_id="DKT-012",
                run_id="RUN-012",
                policy=RetrievalPolicyConfig(
                    enabled=False,
                    top_k=5,
                    min_relevance_score=-1.0,
                    allow_global_fallback=True,
                ),
            )

            self.assertFalse(result.enabled)
            self.assertEqual(result.sources, ())

    def test_policy_from_mapping_applies_configurable_overrides(self) -> None:
        base = RetrievalPolicyConfig(
            enabled=True,
            top_k=3,
            min_relevance_score=0.2,
            allow_global_fallback=True,
        )
        resolved = policy_from_mapping(
            {
                "enabled": False,
                "top_k": 7,
                "min_relevance_score": 0.85,
                "allow_global_fallback": False,
            },
            base=base,
        )

        self.assertFalse(resolved.enabled)
        self.assertEqual(resolved.top_k, 7)
        self.assertEqual(resolved.min_relevance_score, 0.85)
        self.assertFalse(resolved.allow_global_fallback)

    def test_policy_from_mapping_ignores_invalid_values(self) -> None:
        base = RetrievalPolicyConfig(
            enabled=True,
            top_k=2,
            min_relevance_score=0.4,
            allow_global_fallback=False,
        )
        resolved = policy_from_mapping(
            {
                "enabled": "false",
                "top_k": "not-int",
                "min_relevance_score": "bad",
                "allow_global_fallback": "yes",
            },
            base=base,
        )

        self.assertEqual(resolved, base)


if __name__ == "__main__":
    unittest.main()
