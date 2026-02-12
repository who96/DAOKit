from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from rag.retrieval import (
    PolicyAwareRetriever,
    RetrievalPolicyConfig,
    RetrievalResult,
    policy_from_mapping,
)
from state.relay_policy import RelayModePolicy
from state.store import StateStore

from .state_machine import (
    IllegalTransitionError,
    NODE_TRANSITIONS,
    STATUS_TO_NODE,
    OrchestratorStatus,
    guard_transition,
    parse_status,
)


StateMutator = Callable[[dict[str, Any]], None]
DEFAULT_CONTROLLER_LANE = "controller"
ROLE_KEY_CONTROLLER_LANE = "controller_lane"
ROLE_KEY_CONTROLLER_OWNERSHIP = "controller_ownership"


class OrchestratorRuntime:
    """Deterministic orchestrator graph backed by explicit persisted state."""

    def __init__(
        self,
        *,
        task_id: str,
        run_id: str,
        goal: str,
        state_store: StateStore,
        step_id: str = "S1",
        retriever: PolicyAwareRetriever | None = None,
        retrieval_index_path: str | Path | None = None,
        default_retrieval_policies: Mapping[str, RetrievalPolicyConfig] | None = None,
        relay_policy: RelayModePolicy | None = None,
    ) -> None:
        self.task_id = task_id
        self.run_id = run_id
        self.goal = goal
        self.step_id = step_id
        self.state_store = state_store
        self.relay_policy = relay_policy or RelayModePolicy(relay_mode_enabled=False)
        self.retriever = retriever or PolicyAwareRetriever(index_path=retrieval_index_path)
        self._retrieval_cache: dict[str, RetrievalResult] = {}
        self._default_retrieval_policies = {
            "planning": RetrievalPolicyConfig(
                enabled=True,
                top_k=3,
                min_relevance_score=0.2,
                allow_global_fallback=True,
            ),
            "troubleshooting": RetrievalPolicyConfig(
                enabled=True,
                top_k=3,
                min_relevance_score=0.2,
                allow_global_fallback=True,
            ),
        }
        if default_retrieval_policies is not None:
            self._default_retrieval_policies.update(default_retrieval_policies)
        self._bootstrap_ledger()

    def _bootstrap_ledger(self) -> None:
        state = self.state_store.load_state()
        changed = False

        if state.get("task_id") != self.task_id:
            state["task_id"] = self.task_id
            changed = True
        if state.get("run_id") != self.run_id:
            state["run_id"] = self.run_id
            changed = True
        if not state.get("goal"):
            state["goal"] = self.goal
            changed = True
        if "status" not in state:
            state["status"] = OrchestratorStatus.PLANNING.value
            changed = True
        if "role_lifecycle" not in state or not isinstance(state["role_lifecycle"], dict):
            state["role_lifecycle"] = {"orchestrator": "idle"}
            changed = True
        lifecycle = state["role_lifecycle"]
        if not isinstance(lifecycle.get(ROLE_KEY_CONTROLLER_LANE), str) or not lifecycle[
            ROLE_KEY_CONTROLLER_LANE
        ].strip():
            lifecycle[ROLE_KEY_CONTROLLER_LANE] = DEFAULT_CONTROLLER_LANE
            changed = True
        if not isinstance(lifecycle.get(ROLE_KEY_CONTROLLER_OWNERSHIP), str) or not lifecycle[
            ROLE_KEY_CONTROLLER_OWNERSHIP
        ].strip():
            lifecycle[ROLE_KEY_CONTROLLER_OWNERSHIP] = f"{lifecycle[ROLE_KEY_CONTROLLER_LANE]}:unassigned"
            changed = True
        if "succession" not in state or not isinstance(state["succession"], dict):
            state["succession"] = {"enabled": True, "last_takeover_at": None}
            changed = True
        if "steps" not in state or not isinstance(state["steps"], list):
            state["steps"] = []
            changed = True
        if not state["steps"]:
            state["steps"] = [self._default_step_contract()]
            changed = True

        if changed:
            self.state_store.save_state(
                state,
                node="bootstrap",
                from_status=None,
                to_status=state.get("status"),
            )

    def _default_step_contract(self) -> dict[str, Any]:
        return {
            "id": self.step_id,
            "title": "Implement orchestrator state machine",
            "category": "implementation",
            "goal": self.goal,
            "actions": [
                "Implement nodes extract/plan/dispatch/verify/transition",
                "Persist state snapshots between node transitions",
                "Add transition guards for forbidden jumps",
            ],
            "acceptance_criteria": [
                "Graph runs happy path end-to-end",
                "Illegal transition attempts fail with explicit diagnostics",
                "State is recoverable after process restart",
            ],
            "expected_outputs": [
                "report.md",
                "verification.log",
                "audit-summary.md",
            ],
            "dependencies": ["DKT-002"],
            "retrieval_policy": {
                "planning": {
                    "enabled": True,
                    "top_k": 3,
                    "min_relevance_score": 0.2,
                    "allow_global_fallback": True,
                },
                "troubleshooting": {
                    "enabled": True,
                    "top_k": 3,
                    "min_relevance_score": 0.2,
                    "allow_global_fallback": True,
                },
            },
        }

    def recover_state(self) -> dict[str, Any]:
        return self.state_store.load_state()

    def run(self) -> dict[str, Any]:
        while True:
            state = self.recover_state()
            status = parse_status(str(state.get("status")))
            if status == OrchestratorStatus.DONE:
                return state
            next_node = STATUS_TO_NODE.get(status)
            if next_node is None:
                raise IllegalTransitionError(
                    f"No deterministic node mapping for status '{status.value}'."
                )
            getattr(self, next_node)()

    def extract(self) -> dict[str, Any]:
        return self._execute_node("extract", self._mutate_extract)

    def plan(self) -> dict[str, Any]:
        return self._execute_node("plan", self._mutate_plan)

    def dispatch(self) -> dict[str, Any]:
        self.relay_policy.guard_action(action="orchestrator.dispatch")
        return self._execute_node("dispatch", self._mutate_dispatch)

    def verify(self) -> dict[str, Any]:
        self.relay_policy.guard_action(action="orchestrator.verify")
        return self._execute_node("verify", self._mutate_verify)

    def transition(self) -> dict[str, Any]:
        self.relay_policy.guard_action(action="orchestrator.transition")
        return self._execute_node("transition", self._mutate_transition)

    def relay_forward(
        self,
        *,
        message: str,
        relay_context: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.relay_policy.build_relay_payload(
            action="forward",
            relay_context=relay_context,
            payload={"message": message},
        )

    def relay_observe(
        self,
        *,
        snapshot: Mapping[str, Any],
        relay_context: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.relay_policy.build_relay_payload(
            action="observe",
            relay_context=relay_context,
            payload={"snapshot": snapshot},
        )

    def relay_visualize(
        self,
        *,
        snapshot: Mapping[str, Any],
        relay_context: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.relay_policy.build_relay_payload(
            action="visualize",
            relay_context=relay_context,
            payload={"snapshot": snapshot},
        )

    def retrieve_planning_context(self, query: str | None = None) -> RetrievalResult:
        state = self.recover_state()
        return self._retrieve_context_from_state(state, use_case="planning", query=query)

    def retrieve_troubleshooting_context(self, query: str | None = None) -> RetrievalResult:
        state = self.recover_state()
        return self._retrieve_context_from_state(state, use_case="troubleshooting", query=query)

    def latest_retrieval(self, use_case: str) -> RetrievalResult | None:
        return self._retrieval_cache.get(use_case)

    def _execute_node(self, node_name: str, mutator: StateMutator) -> dict[str, Any]:
        expected_source, target_status = NODE_TRANSITIONS[node_name]
        state = self.recover_state()
        current_status = parse_status(str(state.get("status")))
        guard_transition(current=current_status, target=target_status, trigger=node_name)
        if current_status != expected_source:
            raise IllegalTransitionError(
                f"Node '{node_name}' expects source status {expected_source.value}, "
                f"but ledger is at {current_status.value}."
            )

        working_state = json.loads(json.dumps(state))
        mutator(working_state)
        working_state["status"] = target_status.value
        working_state.setdefault("role_lifecycle", {})
        working_state["role_lifecycle"]["orchestrator"] = f"{node_name}_complete"

        saved = self.state_store.save_state(
            working_state,
            node=node_name,
            from_status=current_status.value,
            to_status=target_status.value,
        )
        self.state_store.append_event(
            task_id=str(saved.get("task_id") or self.task_id),
            run_id=str(saved.get("run_id") or self.run_id),
            step_id=saved.get("current_step"),
            event_type="SYSTEM",
            severity="INFO",
            payload={
                "node": node_name,
                "from_status": current_status.value,
                "to_status": target_status.value,
            },
            dedup_key=None,
        )
        return saved

    def _mutate_extract(self, state: dict[str, Any]) -> None:
        state.setdefault("role_lifecycle", {})
        state["role_lifecycle"]["analysis"] = "prepared"

    def _mutate_plan(self, state: dict[str, Any]) -> None:
        planning_context = self._retrieve_context_from_state(state, use_case="planning", query=None)
        state.setdefault("role_lifecycle", {})
        state["role_lifecycle"]["planning_retrieval"] = self._summarize_retrieval(planning_context)
        if not state.get("steps"):
            state["steps"] = [self._default_step_contract()]

    def _mutate_dispatch(self, state: dict[str, Any]) -> None:
        if state.get("current_step") is None and state.get("steps"):
            first_step = state["steps"][0]
            if isinstance(first_step, dict):
                state["current_step"] = first_step.get("id")
        if state.get("current_step") is None:
            state["current_step"] = self.step_id
        active_step = self._normalize_optional_string(state.get("current_step")) or self.step_id
        state["current_step"] = active_step

        role_lifecycle = state.get("role_lifecycle")
        if not isinstance(role_lifecycle, dict):
            role_lifecycle = {}
            state["role_lifecycle"] = role_lifecycle
        controller_lane = self._resolve_controller_lane(role_lifecycle)
        role_lifecycle[ROLE_KEY_CONTROLLER_LANE] = controller_lane
        role_lifecycle[ROLE_KEY_CONTROLLER_OWNERSHIP] = f"{controller_lane}:{active_step}"
        role_lifecycle[f"lane:{controller_lane}"] = f"active_step:{active_step}"
        role_lifecycle[f"step:{active_step}"] = f"owned_by_lane:{controller_lane}"

    def _mutate_verify(self, state: dict[str, Any]) -> None:
        troubleshooting_context = self._retrieve_context_from_state(
            state,
            use_case="troubleshooting",
            query=None,
        )
        state.setdefault("role_lifecycle", {})
        state["role_lifecycle"]["acceptance"] = "passed"
        state["role_lifecycle"]["troubleshooting_retrieval"] = self._summarize_retrieval(
            troubleshooting_context
        )

    def _mutate_transition(self, state: dict[str, Any]) -> None:
        state.setdefault("role_lifecycle", {})
        state["role_lifecycle"]["orchestrator"] = "completed"

    def _retrieve_context_from_state(
        self,
        state: Mapping[str, Any],
        *,
        use_case: str,
        query: str | None,
    ) -> RetrievalResult:
        policy = self._resolve_retrieval_policy(state, use_case=use_case)
        query_text = self._build_retrieval_query(state, use_case=use_case, explicit_query=query)
        result = self.retriever.retrieve(
            use_case=use_case,
            query=query_text,
            task_id=self._normalize_optional_string(state.get("task_id")),
            run_id=self._normalize_optional_string(state.get("run_id")),
            policy=policy,
        )
        self._retrieval_cache[use_case] = result
        return result

    def _resolve_retrieval_policy(
        self,
        state: Mapping[str, Any],
        *,
        use_case: str,
    ) -> RetrievalPolicyConfig:
        base = self._default_retrieval_policies.get(use_case)
        if base is None:
            return RetrievalPolicyConfig()
        step = self._active_step(state)
        if step is None:
            return base

        raw_policy = step.get("retrieval_policy")
        if not isinstance(raw_policy, Mapping):
            return base
        raw_use_case = raw_policy.get(use_case)
        if not isinstance(raw_use_case, Mapping):
            return base
        return policy_from_mapping(raw_use_case, base=base)

    def _active_step(self, state: Mapping[str, Any]) -> Mapping[str, Any] | None:
        raw_steps = state.get("steps")
        if not isinstance(raw_steps, list):
            return None
        steps = [item for item in raw_steps if isinstance(item, Mapping)]
        if not steps:
            return None

        current_step_id = self._normalize_optional_string(state.get("current_step"))
        if current_step_id is not None:
            for step in steps:
                if step.get("id") == current_step_id:
                    return step
        return steps[0]

    def _build_retrieval_query(
        self,
        state: Mapping[str, Any],
        *,
        use_case: str,
        explicit_query: str | None,
    ) -> str:
        if explicit_query is not None and explicit_query.strip():
            return explicit_query.strip()

        step = self._active_step(state)
        goal = self._normalize_optional_string(state.get("goal")) or self.goal
        step_goal = self._normalize_optional_string(step.get("goal")) if step else None
        parts = [use_case, step_goal, goal]
        return " ".join(part for part in parts if part)

    def _summarize_retrieval(self, result: RetrievalResult) -> str:
        if not result.enabled:
            return "disabled"
        return f"{len(result.sources)}_sources"

    def _resolve_controller_lane(self, role_lifecycle: Mapping[str, Any]) -> str:
        candidate = self._normalize_optional_string(role_lifecycle.get(ROLE_KEY_CONTROLLER_LANE))
        if candidate is not None:
            return candidate
        return DEFAULT_CONTROLLER_LANE

    def _normalize_optional_string(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized if normalized else None
