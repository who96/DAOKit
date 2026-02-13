from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any, Mapping
import unittest

from contracts.validator import validate_payload
from orchestrator.langgraph_runtime import LangGraphOrchestratorRuntime
from orchestrator.state_machine import IllegalTransitionError
from state.store import StateStore


class _FakeCompiledGraph:
    def __init__(self, graph: Any, end_node: str) -> None:
        self._graph = graph
        self._end_node = end_node

    def invoke(self, state: Mapping[str, Any]) -> Mapping[str, Any]:
        working_state: dict[str, Any] = dict(state)
        current_node = self._graph.entry_point
        if not isinstance(current_node, str):
            raise AssertionError("entry point is missing")

        for _ in range(32):
            node_fn = self._graph.nodes[current_node]
            node_output = node_fn(working_state)
            if isinstance(node_output, Mapping):
                working_state.update(node_output)

            if current_node in self._graph.conditional_edges:
                route_fn, route_map = self._graph.conditional_edges[current_node]
                route_key = route_fn(working_state)
                if route_key not in route_map:
                    raise AssertionError(f"unknown route key '{route_key}' for node '{current_node}'")
                next_node = route_map[route_key]
            else:
                next_nodes = self._graph.edges.get(current_node, [])
                if not next_nodes:
                    raise AssertionError(f"node '{current_node}' has no outgoing edges")
                next_node = next_nodes[0]

            if next_node == self._end_node:
                return working_state
            current_node = next_node
        raise AssertionError("conditional route execution exceeded guard iteration limit")


class _FakeStateGraph:
    def __init__(self, _state_type: type[dict[str, Any]], end_node: str) -> None:
        self._end_node = end_node
        self.nodes: dict[str, Any] = {}
        self.edges: dict[str, list[str]] = {}
        self.conditional_edges: dict[str, tuple[Any, dict[str, str]]] = {}
        self.entry_point: str | None = None

    def add_node(self, node_name: str, fn: Any) -> None:
        self.nodes[node_name] = fn

    def set_entry_point(self, node_name: str) -> None:
        self.entry_point = node_name

    def add_edge(self, source: str, target: str) -> None:
        self.edges.setdefault(source, []).append(target)

    def add_conditional_edges(self, source: str, route_fn: Any, route_map: dict[str, str]) -> None:
        self.conditional_edges[source] = (route_fn, dict(route_map))

    def compile(self) -> _FakeCompiledGraph:
        return _FakeCompiledGraph(self, end_node=self._end_node)


class _FakeLangGraphModule:
    END = "__end__"

    def __init__(self) -> None:
        module = self

        class StateGraph:
            def __init__(self, state_type: type[dict[str, Any]]) -> None:
                module.last_graph = _FakeStateGraph(state_type, end_node=module.END)

            def add_node(self, node_name: str, fn: Any) -> None:
                module.last_graph.add_node(node_name, fn)

            def set_entry_point(self, node_name: str) -> None:
                module.last_graph.set_entry_point(node_name)

            def add_edge(self, source: str, target: str) -> None:
                module.last_graph.add_edge(source, target)

            def add_conditional_edges(self, source: str, route_fn: Any, route_map: dict[str, str]) -> None:
                module.last_graph.add_conditional_edges(source, route_fn, route_map)

            def compile(self) -> _FakeCompiledGraph:
                return module.last_graph.compile()

        self.StateGraph = StateGraph
        self.last_graph: _FakeStateGraph | None = None


class LangGraphOrchestratorRuntimeTests(unittest.TestCase):
    def _new_runtime(self, root: Path, run_id: str = "RUN-LG-001") -> LangGraphOrchestratorRuntime:
        return LangGraphOrchestratorRuntime(
            task_id="DKT-030",
            run_id=run_id,
            goal="Implement LangGraph orchestrator runtime",
            state_store=StateStore(root / "state"),
            step_id="S1",
            langgraph_available=False,
            missing_optional_dependencies=("langchain", "langgraph"),
        )

    def _contracts_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "contracts"

    def test_happy_path_runs_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._new_runtime(Path(tmp))

            final_state = runtime.run()
            snapshots = runtime.state_store.list_snapshots()
            transition_nodes = [entry.get("node") for entry in snapshots]

            self.assertEqual(final_state["status"], "DONE")
            self.assertEqual(final_state["current_step"], "S1")
            self.assertEqual(runtime.graph_backend, "fallback")
            self.assertEqual(
                [name for name in transition_nodes if name in {"extract", "plan", "dispatch", "verify", "transition"}],
                ["extract", "plan", "dispatch", "verify", "transition"],
            )

    def test_illegal_transition_reports_explicit_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._new_runtime(Path(tmp))

            with self.assertRaises(IllegalTransitionError) as ctx:
                runtime.transition()

            message = str(ctx.exception)
            self.assertIn("Illegal transition", message)
            self.assertIn("transition", message)
            self.assertIn("PLANNING -> DONE", message)
            self.assertIn("Allowed targets from PLANNING: ANALYSIS", message)

    def test_langgraph_path_uses_conditional_edges_and_rework_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph_module = _FakeLangGraphModule()
            runtime = LangGraphOrchestratorRuntime(
                task_id="DKT-065",
                run_id="RUN-LG-COND-001",
                goal="Exercise conditional route policy",
                state_store=StateStore(Path(tmp) / "state"),
                step_id="S1",
                langgraph_available=True,
                missing_optional_dependencies=(),
                import_module=lambda _name: graph_module,
            )
            bootstrapped = runtime.recover_state()
            bootstrapped["status"] = "ACCEPT"
            bootstrapped.setdefault("role_lifecycle", {})
            bootstrapped["role_lifecycle"]["acceptance"] = "failed"
            runtime.state_store.save_state(
                bootstrapped,
                node="seed_accept_failed",
                from_status="ACCEPT",
                to_status="ACCEPT",
            )

            final_state = runtime.run()
            self.assertEqual(runtime.graph_backend, "langgraph")
            self.assertEqual(final_state["status"], "DONE")

            transition_nodes = [
                item.get("node")
                for item in runtime.state_store.list_snapshots()
                if item.get("node") in {"verify", "transition"}
            ]
            self.assertEqual(transition_nodes, ["transition", "verify", "transition"])
            self.assertEqual(final_state["role_lifecycle"]["route:last_id"], "transition.acceptance_not_failed.done")
            self.assertEqual(final_state["role_lifecycle"]["route:last_reason"], "acceptance_not_failed_finalize")

            self.assertIsNotNone(graph_module.last_graph)
            assert graph_module.last_graph is not None
            self.assertIn("transition", graph_module.last_graph.conditional_edges)
            transition_edge_map = graph_module.last_graph.conditional_edges["transition"][1]
            self.assertEqual(
                sorted(transition_edge_map.keys()),
                [
                    "transition.acceptance_failed.rework",
                    "transition.acceptance_not_failed.done",
                ],
            )

    def test_ledger_writes_stay_contract_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._new_runtime(Path(tmp))
            runtime.run()

            pipeline_state = json.loads(runtime.state_store.pipeline_state_path.read_text(encoding="utf-8"))
            validate_payload(
                "pipeline_state",
                pipeline_state,
                contracts_dir=self._contracts_dir(),
            )

            event_lines = runtime.state_store.events_path.read_text(encoding="utf-8").splitlines()
            events = [json.loads(line) for line in event_lines if line.strip()]

            self.assertGreaterEqual(len(events), 5)
            for event in events:
                validate_payload(
                    "events",
                    event,
                    contracts_dir=self._contracts_dir(),
                )


if __name__ == "__main__":
    unittest.main()
