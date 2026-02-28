from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from contracts.runtime_adapters import RuntimeRelayPolicy, RuntimeRetriever
from rag.retrieval import RetrievalPolicyConfig
from state.backend import StateBackend
from .runtime import DEFAULT_DISPATCH_MAX_RESUME_RETRIES, DEFAULT_DISPATCH_MAX_REWORK_ATTEMPTS

from .runtime import OrchestratorRuntime, RuntimeDispatchAdapter
from .state_machine import (
    STATUS_TO_NODE,
    IllegalTransitionError,
    OrchestratorStatus,
    conditional_routes_for_node,
    parse_status,
)


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
        state_store: StateBackend,
        step_id: str = "S1",
        retriever: RuntimeRetriever | None = None,
        retrieval_index_path: str | Path | None = None,
        default_retrieval_policies: Mapping[str, RetrievalPolicyConfig] | None = None,
        relay_policy: RuntimeRelayPolicy | None = None,
        dispatch_adapter: RuntimeDispatchAdapter | None = None,
        dispatch_max_resume_retries: int = DEFAULT_DISPATCH_MAX_RESUME_RETRIES,
        dispatch_max_rework_attempts: int = DEFAULT_DISPATCH_MAX_REWORK_ATTEMPTS,
        llm_client: Any | None = None,
        workspace_base_dir: str | Path | None = None,
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
            llm_client=llm_client,
            workspace_base_dir=workspace_base_dir,
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
        entry_node = STATUS_TO_NODE.get(start_status)
        if entry_node is None:
            raise IllegalTransitionError(
                f"No deterministic node mapping for status '{start_status.value}'."
            )

        ordered_nodes: list[str] = []
        queue: list[str] = [entry_node]
        seen: set[str] = set()
        while queue:
            node_name = queue.pop(0)
            if node_name in seen:
                continue
            seen.add(node_name)
            ordered_nodes.append(node_name)
            for route in conditional_routes_for_node(node_name):
                if route.target == OrchestratorStatus.DONE:
                    continue
                next_node = STATUS_TO_NODE.get(route.target)
                if next_node is None:
                    raise IllegalTransitionError(
                        f"Conditional route '{route.route_id}' from node '{node_name}' points to "
                        f"status '{route.target.value}' without a deterministic node mapping. "
                        "Action: define the missing node mapping before enabling this route.",
                        diagnostics={
                            "diagnostic_type": "route_target_missing_node",
                            "node": node_name,
                            "route_id": route.route_id,
                            "target_status": route.target.value,
                        },
                    )
                queue.append(next_node)
        return ordered_nodes

    def _compile_langgraph(self, *, node_sequence: list[str]) -> _CompiledLifecycleGraph:
        graph_module = self._import_module("langgraph.graph")
        state_graph_type = getattr(graph_module, "StateGraph")
        graph_builder = state_graph_type(dict)
        add_conditional_edges = getattr(graph_builder, "add_conditional_edges", None)
        if not callable(add_conditional_edges):
            raise IllegalTransitionError(
                "LangGraph StateGraph is missing 'add_conditional_edges' required for deterministic "
                "conditional routing. Action: install a compatible LangGraph version or use fallback mode."
            )

        end_node = getattr(graph_module, "END", "__end__")

        for node_name in node_sequence:
            graph_builder.add_node(node_name, self._build_node(node_name))

        graph_builder.set_entry_point(node_sequence[0])
        for node_name in node_sequence:
            route_map = self._build_route_map(node_name=node_name, end_node=end_node)
            add_conditional_edges(
                node_name,
                self._build_route_selector(node_name=node_name, route_map=route_map),
                route_map,
            )
        return graph_builder.compile()

    def _build_route_map(self, *, node_name: str, end_node: str) -> dict[str, str]:
        route_map: dict[str, str] = {}
        for route in conditional_routes_for_node(node_name):
            if route.target == OrchestratorStatus.DONE:
                route_map[route.route_id] = end_node
                continue

            next_node = STATUS_TO_NODE.get(route.target)
            if next_node is None:
                raise IllegalTransitionError(
                    f"Conditional route '{route.route_id}' from node '{node_name}' points to "
                    f"status '{route.target.value}' without a deterministic node mapping. "
                    "Action: define STATUS_TO_NODE mapping for this status.",
                    diagnostics={
                        "diagnostic_type": "route_target_missing_node",
                        "node": node_name,
                        "route_id": route.route_id,
                        "target_status": route.target.value,
                    },
                )
            route_map[route.route_id] = next_node

        if not route_map:
            raise IllegalTransitionError(
                f"Node '{node_name}' has no conditional routes configured. "
                "Action: add at least one explicit route predicate for this node.",
                diagnostics={
                    "diagnostic_type": "route_policy_empty",
                    "node": node_name,
                },
            )
        return route_map

    def _build_route_selector(
        self,
        *,
        node_name: str,
        route_map: Mapping[str, str],
    ) -> Callable[[Mapping[str, Any]], str]:
        route_by_target: dict[OrchestratorStatus, str] = {}
        for route in conditional_routes_for_node(node_name):
            route_by_target.setdefault(route.target, route.route_id)

        def _route_selector(state: Mapping[str, Any]) -> str:
            route_id = state.get("route_id")
            if isinstance(route_id, str) and route_id in route_map:
                return route_id

            lifecycle = state.get("role_lifecycle")
            if isinstance(lifecycle, Mapping):
                lifecycle_route_id = lifecycle.get("route:last_id")
                if isinstance(lifecycle_route_id, str) and lifecycle_route_id in route_map:
                    return lifecycle_route_id

            status = parse_status(str(state.get("status")))
            fallback_route_id = route_by_target.get(status)
            if fallback_route_id is not None:
                return fallback_route_id

            raise IllegalTransitionError(
                f"LangGraph route selector for node '{node_name}' could not resolve a route key "
                f"from state status '{status.value}'. Action: ensure node output includes route metadata "
                "or a valid target status.",
                diagnostics={
                    "diagnostic_type": "route_selector_no_match",
                    "node": node_name,
                    "current_status": status.value,
                    "route_keys": sorted(route_map),
                },
            )

        return _route_selector

    def _build_node(self, node_name: str) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
        def _node(_state: Mapping[str, Any]) -> Mapping[str, Any]:
            next_state = getattr(self, node_name)()
            output: dict[str, Any] = {"status": str(next_state.get("status"))}
            lifecycle = next_state.get("role_lifecycle")
            if isinstance(lifecycle, Mapping):
                route_id = lifecycle.get("route:last_id")
                if isinstance(route_id, str) and route_id:
                    output["route_id"] = route_id
            return output

        return _node
