from __future__ import annotations

from pathlib import Path
import tempfile
import types
import unittest

from rag.ingest.pipeline import FileIngestionItem, rebuild_index
from tools.function_calling.adapter import FunctionCallingAdapter
from tools.langchain.orchestration import ToolOrchestrationLayer, ToolOrchestrationMode
from tools.mcp.adapter import McpAdapter


class LangChainRetrievalBridgeTests(unittest.TestCase):
    def _build_index(self, root: Path) -> Path:
        docs_dir = root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        planning = docs_dir / "planning.md"
        planning.write_text(
            "langchain planning retrieval bridge source attribution relevance",
            encoding="utf-8",
        )
        troubleshooting = docs_dir / "troubleshooting.log"
        troubleshooting.write_text(
            "langchain troubleshooting retrieval bridge confidence and relevance score",
            encoding="utf-8",
        )

        index_path = root / "rag-index.json"
        rebuild_index(
            [
                FileIngestionItem(path=planning, task_id="DKT-033", run_id="RUN-LC"),
                FileIngestionItem(path=troubleshooting, task_id="DKT-033", run_id="RUN-LC"),
            ],
            index_path=index_path,
        )
        return index_path

    def _new_layer(self, index_path: Path) -> ToolOrchestrationLayer:
        return ToolOrchestrationLayer(
            function_calling_adapter=FunctionCallingAdapter(),
            mcp_adapter=McpAdapter(),
            requested_mode=ToolOrchestrationMode.LANGCHAIN.value,
            retrieval_index_path=index_path,
            import_module=lambda _name: types.SimpleNamespace(__name__="langchain"),
        )

    def test_langchain_retrieval_returns_sources_and_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layer = self._new_layer(self._build_index(root))

            result = layer.invoke_retrieval(
                task_id="DKT-033",
                run_id="RUN-LC",
                step_id="S1",
                use_case="planning",
                query="planning retrieval source attribution relevance",
                policy={"top_k": 5, "min_relevance_score": -1.0},
            )

            self.assertTrue(result.enabled)
            self.assertGreaterEqual(len(result.sources), 1)
            self.assertTrue(result.sources[0].source_path)
            self.assertIsInstance(result.sources[0].relevance_score, float)

            documents = layer.invoke_retrieval_documents(
                task_id="DKT-033",
                run_id="RUN-LC",
                step_id="S1",
                use_case="planning",
                query="planning retrieval source attribution relevance",
                policy={"top_k": 5, "min_relevance_score": -1.0},
            )
            self.assertGreaterEqual(len(documents), 1)
            first_document = documents[0]
            self.assertIn("source_path", first_document["metadata"])
            self.assertIn("relevance_score", first_document["metadata"])

            traces = layer.trace_logs()
            retrieval_trace = traces[-1]
            self.assertEqual(retrieval_trace.adapter, "retrieval")
            self.assertEqual(retrieval_trace.operation, "planning")
            self.assertEqual(retrieval_trace.payload["source_count"], len(result.sources))

    def test_langchain_retrieval_policy_is_configurable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layer = self._new_layer(self._build_index(root))

            broad = layer.invoke_retrieval(
                task_id="DKT-033",
                run_id="RUN-LC",
                step_id="S1",
                use_case="troubleshooting",
                query="troubleshooting retrieval confidence relevance score",
                policy={"top_k": 5, "min_relevance_score": -1.0},
            )
            self.assertGreaterEqual(len(broad.sources), 1)

            strict = layer.invoke_retrieval(
                task_id="DKT-033",
                run_id="RUN-LC",
                step_id="S1",
                use_case="troubleshooting",
                query="troubleshooting retrieval confidence relevance score",
                policy={
                    "top_k": 5,
                    "min_relevance_score": broad.sources[0].relevance_score + 1e-6,
                },
            )
            self.assertEqual(strict.sources, ())

            disabled = layer.invoke_retrieval(
                task_id="DKT-033",
                run_id="RUN-LC",
                step_id="S1",
                use_case="planning",
                query="planning retrieval source attribution relevance",
                policy={"enabled": False},
            )
            self.assertFalse(disabled.enabled)
            self.assertEqual(disabled.sources, ())


if __name__ == "__main__":
    unittest.main()
