from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from contracts.runtime_adapters import RuntimeRelayPolicy, RuntimeRetriever, RuntimeStateStore
from rag.retrieval import RetrievalPolicyConfig
from .runtime import DEFAULT_DISPATCH_MAX_RESUME_RETRIES, DEFAULT_DISPATCH_MAX_REWORK_ATTEMPTS

from .runtime import OrchestratorRuntime, RuntimeDispatchAdapter
from .state_machine import NODE_TRANSITIONS, STATUS_TO_NODE, IllegalTransitionError, OrchestratorStatus, parse_status


ImportModule = Callable[[str], Any]


class _CompiledLifecycleGraph(Protocol):
    def invoke(self, state: Mapping[str, Any]) -> Mapping[str, Any]: ...


class LangGraphOrchestratorRuntime(OrchestratorRuntime):
    """Orchestrator runtime that executes lifecycle transitions through a graph runner."""

    def __init__(
        self,
        *,
        task_id: str,
        run_id: str,
        goal: str,
        state_store: RuntimeStateStore,
        step_id: str = "S1",
        retriever: RuntimeRetriever | None = None,
        retrieval_index_path: str | Path | None = None,
        default_retrieval_policies: Mapping[str, RetrievalPolicyConfig] | None = None,
        relay_policy: RuntimeRelayPolicy | None = None,
        dispatch_adapter: RuntimeDispatchAdapter | None = None,
        dispatch_max_resume_retries: int = DEFAULT_DISPATCH_MAX_RESUME_RETRIES,
        dispatch_max_rework_attempts: int = DEFAULT_DISPATCH_MAX_REWORK_ATTEMPTS,
        langgraph_available: bool = False,
        missing_optional_dependencies: tuple[str, ...] = (),
        import_module: ImportModule | None = None,
    ) -> None:
        super().__init__(
            task_id=task_id,
            run_id=run_id,
            goal=goal,
            state_store=state_store,
            step_id=step_id,
            retriever=retriever,
            retrieval_index_path=retrieval_index_path,
            default_retrieval_policies=default_retrieval_policies,
            relay_policy=relay_policy,
            dispatch_adapter=dispatch_adapter,
            dispatch_max_resume_retries=dispatch_max_resume_retries,
            dispatch_max_rework_attempts=dispatch_max_rework_attempts,
        )
        self.langgraph_available = bool(langgraph_available)
        self.missing_optional_dependencies = tuple(missing_optional_dependencies)
        self.graph_backend = "langgraph" if self.langgraph_available else "fallback"
        self._import_module = import_module or importlib.import_module
        self._graph_warnings: list[str] = []

    @property
    def graph_warnings(self) -> tuple[str, ...]:
        return tuple(self._graph_warnings)

    def _default_step_contract(self) -> dict[str, Any]:
        contract = super()._default_step_contract()
        contract.pop("retrieval_policy", None)
        return contract

    def run(self) -> dict[str, Any]:
        current_state = self.recover_state()
        current_status = parse_status(str(current_state.get("status")))
        if current_status == OrchestratorStatus.DONE:
            return current_state

        if self.langgraph_available:
            try:
                return self._run_with_langgraph(start_status=current_status)
            except Exception as exc:  # pragma: no cover - exercised when langgraph is installed.
                self.graph_backend = "fallback"
                self._graph_warnings.append(
                    f"langgraph runtime unavailable at execution time: {exc.__class__.__name__}"
                )
        return self._run_with_fallback(start_status=current_status)

    def _run_with_langgraph(self, *, start_status: OrchestratorStatus) -> dict[str, Any]:
        node_sequence = self._node_sequence_from_status(start_status)
        if not node_sequence:
            return self.recover_state()
        compiled = self._compile_langgraph(node_sequence=node_sequence)
        compiled.invoke({"status": start_status.value})
        return self.recover_state()

    def _run_with_fallback(self, *, start_status: OrchestratorStatus) -> dict[str, Any]:
        current_status = start_status
        while current_status != OrchestratorStatus.DONE:
            node_name = STATUS_TO_NODE.get(current_status)
            if node_name is None:
                raise IllegalTransitionError(
                    f"No deterministic node mapping for status '{current_status.value}'."
                )
            next_state = getattr(self, node_name)()
            current_status = parse_status(str(next_state.get("status")))
        return self.recover_state()

    def _node_sequence_from_status(self, start_status: OrchestratorStatus) -> list[str]:
        nodes: list[str] = []
        current = start_status
        while current != OrchestratorStatus.DONE:
            node_name = STATUS_TO_NODE.get(current)
            if node_name is None:
                raise IllegalTransitionError(
                    f"No deterministic node mapping for status '{current.value}'."
                )
            nodes.append(node_name)
            _, target = NODE_TRANSITIONS[node_name]
            current = target
        return nodes

    def _compile_langgraph(self, *, node_sequence: list[str]) -> _CompiledLifecycleGraph:
        graph_module = self._import_module("langgraph.graph")
        state_graph_type = getattr(graph_module, "StateGraph")
        graph_builder = state_graph_type(dict)

        for node_name in node_sequence:
            graph_builder.add_node(node_name, self._build_node(node_name))

        graph_builder.set_entry_point(node_sequence[0])
        for source, target in zip(node_sequence, node_sequence[1:]):
            graph_builder.add_edge(source, target)

        end_node = getattr(graph_module, "END", "__end__")
        graph_builder.add_edge(node_sequence[-1], end_node)
        return graph_builder.compile()

    def _build_node(self, node_name: str) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
        def _node(_state: Mapping[str, Any]) -> Mapping[str, Any]:
            next_state = getattr(self, node_name)()
            return {"status": str(next_state.get("status"))}

        return _node
