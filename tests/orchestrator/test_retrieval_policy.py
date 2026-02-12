from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from orchestrator.langgraph_runtime import LangGraphOrchestratorRuntime
from orchestrator.runtime import OrchestratorRuntime
from rag.ingest.pipeline import FileIngestionItem, rebuild_index
from rag.retrieval import RetrievalPolicyConfig
from state.store import StateStore


class OrchestratorRetrievalPolicyTests(unittest.TestCase):
    def _build_index(self, root: Path) -> Path:
        docs_dir = root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        planning = docs_dir / "plan.md"
        planning.write_text(
            "orchestrator planning retrieval context with source attribution",
            encoding="utf-8",
        )
        troubleshooting = docs_dir / "troubleshoot.log"
        troubleshooting.write_text(
            "troubleshooting retrieval suggestions for acceptance failures",
            encoding="utf-8",
        )

        index_path = root / "rag-index.json"
        rebuild_index(
            [
                FileIngestionItem(path=planning, task_id="DKT-012", run_id="RUN-ORCH"),
                FileIngestionItem(path=troubleshooting, task_id="DKT-012", run_id="RUN-ORCH"),
            ],
            index_path=index_path,
        )
        return index_path

    def _new_runtime(
        self,
        root: Path,
        *,
        index_path: Path,
        run_id: str = "RUN-ORCH",
    ) -> OrchestratorRuntime:
        return OrchestratorRuntime(
            task_id="DKT-012",
            run_id=run_id,
            goal="Integrate retrieval policies into orchestrator",
            state_store=StateStore(root / "state"),
            step_id="S1",
            retrieval_index_path=index_path,
            default_retrieval_policies={
                "planning": RetrievalPolicyConfig(
                    enabled=True,
                    top_k=4,
                    min_relevance_score=-1.0,
                    allow_global_fallback=True,
                ),
                "troubleshooting": RetrievalPolicyConfig(
                    enabled=True,
                    top_k=4,
                    min_relevance_score=-1.0,
                    allow_global_fallback=True,
                ),
            },
        )

    def _new_langgraph_runtime(
        self,
        root: Path,
        *,
        index_path: Path,
        run_id: str = "RUN-ORCH",
    ) -> LangGraphOrchestratorRuntime:
        return LangGraphOrchestratorRuntime(
            task_id="DKT-012",
            run_id=run_id,
            goal="Integrate retrieval policies into orchestrator",
            state_store=StateStore(root / "state"),
            step_id="S1",
            retrieval_index_path=index_path,
            default_retrieval_policies={
                "planning": RetrievalPolicyConfig(
                    enabled=True,
                    top_k=4,
                    min_relevance_score=-1.0,
                    allow_global_fallback=True,
                ),
                "troubleshooting": RetrievalPolicyConfig(
                    enabled=True,
                    top_k=4,
                    min_relevance_score=-1.0,
                    allow_global_fallback=True,
                ),
            },
            langgraph_available=False,
            missing_optional_dependencies=("langchain", "langgraph"),
        )

    def test_orchestrator_retrieval_returns_sources_and_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = self._build_index(root)
            runtime = self._new_runtime(root, index_path=index_path)

            result = runtime.retrieve_planning_context("planning retrieval source attribution")

            self.assertTrue(result.enabled)
            self.assertGreaterEqual(len(result.sources), 1)
            self.assertTrue(result.sources[0].source_path)
            self.assertIsInstance(result.sources[0].relevance_score, float)
            self.assertEqual(runtime.latest_retrieval("planning"), result)

    def test_disabling_retrieval_does_not_break_core_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = self._build_index(root)
            runtime = self._new_runtime(root, index_path=index_path)

            state = runtime.recover_state()
            state["steps"][0]["retrieval_policy"] = {
                "planning": {"enabled": False},
                "troubleshooting": {"enabled": False},
            }
            runtime.state_store.save_state(
                state,
                node="test_setup_disable_retrieval",
                from_status=state.get("status"),
                to_status=state.get("status"),
            )

            final_state = runtime.run()
            planning_context = runtime.latest_retrieval("planning")
            troubleshooting_context = runtime.latest_retrieval("troubleshooting")

            self.assertEqual(final_state["status"], "DONE")
            self.assertIsNotNone(planning_context)
            self.assertIsNotNone(troubleshooting_context)
            self.assertFalse(planning_context.enabled if planning_context else True)
            self.assertFalse(troubleshooting_context.enabled if troubleshooting_context else True)
            self.assertEqual(planning_context.sources if planning_context else None, ())
            self.assertEqual(troubleshooting_context.sources if troubleshooting_context else None, ())

    def test_retrieval_only_calls_do_not_mutate_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = self._build_index(root)
            runtime = self._new_runtime(root, index_path=index_path)

            state_bytes_before = runtime.state_store.pipeline_state_path.read_bytes()
            snapshots_before = runtime.state_store.list_snapshots()
            events_before = runtime.state_store.events_path.read_text(encoding="utf-8")

            runtime.retrieve_planning_context("planning retrieval source attribution")
            runtime.retrieve_troubleshooting_context("troubleshooting retrieval failures")

            state_bytes_after = runtime.state_store.pipeline_state_path.read_bytes()
            snapshots_after = runtime.state_store.list_snapshots()
            events_after = runtime.state_store.events_path.read_text(encoding="utf-8")

            self.assertEqual(state_bytes_before, state_bytes_after)
            self.assertEqual(snapshots_before, snapshots_after)
            self.assertEqual(events_before, events_after)

    def test_langgraph_runtime_retrieval_returns_sources_and_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = self._build_index(root)
            runtime = self._new_langgraph_runtime(root, index_path=index_path)

            planning = runtime.retrieve_planning_context("planning retrieval source attribution")
            troubleshooting = runtime.retrieve_troubleshooting_context(
                "troubleshooting retrieval acceptance failures"
            )

            self.assertTrue(planning.enabled)
            self.assertTrue(troubleshooting.enabled)
            self.assertGreaterEqual(len(planning.sources), 1)
            self.assertGreaterEqual(len(troubleshooting.sources), 1)
            self.assertTrue(planning.sources[0].source_path)
            self.assertIsInstance(planning.sources[0].relevance_score, float)
            self.assertTrue(troubleshooting.sources[0].source_path)
            self.assertIsInstance(troubleshooting.sources[0].relevance_score, float)

    def test_langgraph_retrieval_policy_is_configurable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = self._build_index(root)
            runtime = LangGraphOrchestratorRuntime(
                task_id="DKT-012",
                run_id="RUN-ORCH",
                goal="Integrate retrieval policies into orchestrator",
                state_store=StateStore(root / "state"),
                step_id="S1",
                retrieval_index_path=index_path,
                default_retrieval_policies={
                    "planning": RetrievalPolicyConfig(
                        enabled=False,
                        top_k=2,
                        min_relevance_score=0.9,
                        allow_global_fallback=False,
                    ),
                    "troubleshooting": RetrievalPolicyConfig(
                        enabled=False,
                        top_k=2,
                        min_relevance_score=0.9,
                        allow_global_fallback=False,
                    ),
                },
                langgraph_available=False,
                missing_optional_dependencies=("langchain", "langgraph"),
            )

            planning = runtime.retrieve_planning_context("planning retrieval source attribution")
            troubleshooting = runtime.retrieve_troubleshooting_context(
                "troubleshooting retrieval acceptance failures"
            )

            self.assertFalse(planning.enabled)
            self.assertFalse(troubleshooting.enabled)
            self.assertEqual(planning.sources, ())
            self.assertEqual(troubleshooting.sources, ())

    def test_langgraph_retrieval_only_calls_do_not_mutate_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = self._build_index(root)
            runtime = self._new_langgraph_runtime(root, index_path=index_path)

            state_bytes_before = runtime.state_store.pipeline_state_path.read_bytes()
            snapshots_before = runtime.state_store.list_snapshots()
            events_before = runtime.state_store.events_path.read_text(encoding="utf-8")

            runtime.retrieve_planning_context("planning retrieval source attribution")
            runtime.retrieve_troubleshooting_context("troubleshooting retrieval failures")

            state_bytes_after = runtime.state_store.pipeline_state_path.read_bytes()
            snapshots_after = runtime.state_store.list_snapshots()
            events_after = runtime.state_store.events_path.read_text(encoding="utf-8")

            self.assertEqual(state_bytes_before, state_bytes_after)
            self.assertEqual(snapshots_before, snapshots_after)
            self.assertEqual(events_before, events_after)


if __name__ == "__main__":
    unittest.main()
