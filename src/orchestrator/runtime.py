from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from contracts.runtime_adapters import RuntimeRelayPolicy, RuntimeRetriever, RuntimeStateStore
from dispatch.shim_adapter import DispatchCallResult
from planner.text_input_plan import build_minimal_text_input_steps
from rag.retrieval import (
    PolicyAwareRetriever,
    RetrievalPolicyConfig,
    RetrievalResult,
    policy_from_mapping,
)
from state.relay_policy import RelayModePolicy

from .state_machine import (
    IllegalTransitionError,
    NODE_TRANSITIONS,
    STATUS_TO_NODE,
    OrchestratorStatus,
    parse_status,
    resolve_conditional_route,
)


StateMutator = Callable[[dict[str, Any]], None]
DEFAULT_CONTROLLER_LANE = "controller"
ROLE_KEY_CONTROLLER_LANE = "controller_lane"
ROLE_KEY_CONTROLLER_OWNERSHIP = "controller_ownership"
DEFAULT_DISPATCH_MAX_RESUME_RETRIES = 1
DEFAULT_DISPATCH_MAX_REWORK_ATTEMPTS = 1
STEP_CONTRACT_FIELDS = (
    "id",
    "title",
    "category",
    "goal",
    "actions",
    "acceptance_criteria",
    "expected_outputs",
    "dependencies",
)


class RuntimeDispatchAdapter(Protocol):
    def create(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        request: Mapping[str, Any] | None = None,
        thread_id: str | None = None,
        retry_index: int = 0,
        dry_run: bool = False,
    ) -> DispatchCallResult: ...

    def resume(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        request: Mapping[str, Any] | None = None,
        thread_id: str | None = None,
        retry_index: int = 0,
        dry_run: bool = False,
    ) -> DispatchCallResult: ...

    def rework(
        self,
        *,
        task_id: str,
        run_id: str,
        step_id: str,
        request: Mapping[str, Any] | None = None,
        thread_id: str | None = None,
        retry_index: int = 0,
        dry_run: bool = False,
        rework_context: Mapping[str, Any] | None = None,
    ) -> DispatchCallResult: ...


class OrchestratorRuntime:
    """Deterministic orchestrator graph backed by explicit persisted state."""

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
    ) -> None:
        self.task_id = task_id
        self.run_id = run_id
        self.goal = goal
        self.step_id = step_id
        self.state_store = state_store
        self.relay_policy = relay_policy or RelayModePolicy(relay_mode_enabled=False)
        self.dispatch_adapter = dispatch_adapter
        self.dispatch_max_resume_retries = self._normalize_non_negative_int(
            dispatch_max_resume_retries,
            name="dispatch_max_resume_retries",
        )
        self.dispatch_max_rework_attempts = self._normalize_non_negative_int(
            dispatch_max_rework_attempts,
            name="dispatch_max_rework_attempts",
        )
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
            "planner_source": "bootstrap_default",
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
        expected_source, _default_target = NODE_TRANSITIONS[node_name]
        state = self.recover_state()
        current_status = parse_status(str(state.get("status")))
        try:
            route = resolve_conditional_route(
                node_name=node_name,
                current=current_status,
                state=state,
            )
        except IllegalTransitionError as exc:
            self._append_route_failure_event(
                node_name=node_name,
                current_status=current_status,
                state=state,
                error=exc,
            )
            raise

        if current_status != expected_source:
            mismatch_error = IllegalTransitionError(
                f"Node '{node_name}' expects source status {expected_source.value}, "
                f"but ledger is at {current_status.value}. "
                "Action: resume from the expected predecessor node before retrying this node.",
                diagnostics={
                    "diagnostic_type": "route_source_mismatch",
                    "node": node_name,
                    "current_status": current_status.value,
                    "expected_source": expected_source.value,
                    "attempted_target": route.target.value,
                    "route_id": route.route_id,
                    "route_reason": route.reason,
                    "predicate_name": route.predicate_name,
                },
            )
            self._append_route_failure_event(
                node_name=node_name,
                current_status=current_status,
                state=state,
                error=mismatch_error,
            )
            raise mismatch_error

        working_state = json.loads(json.dumps(state))
        mutator(working_state)
        working_state["status"] = route.target.value
        working_state.setdefault("role_lifecycle", {})
        working_state["role_lifecycle"]["orchestrator"] = f"{node_name}_complete"
        working_state["role_lifecycle"]["route:last_node"] = node_name
        working_state["role_lifecycle"]["route:last_id"] = route.route_id
        working_state["role_lifecycle"]["route:last_reason"] = route.reason
        working_state["role_lifecycle"]["route:last_predicate"] = route.predicate_name
        working_state["role_lifecycle"]["route:last_target"] = route.target.value
        route_trace = self._append_route_trace(
            role_lifecycle=working_state["role_lifecycle"],
            route_id=route.route_id,
        )
        route_trace_index = len(route_trace) - 1
        correlation_id = self._resolve_route_correlation_id(state=working_state)
        route_trace_id = self._resolve_route_trace_id(state=working_state)
        working_state["role_lifecycle"]["route:trace_id"] = route_trace_id
        working_state["role_lifecycle"]["route:trace_index"] = str(route_trace_index)
        if correlation_id is not None:
            working_state["role_lifecycle"]["route:correlation_id"] = correlation_id

        saved = self.state_store.save_state(
            working_state,
            node=node_name,
            from_status=current_status.value,
            to_status=route.target.value,
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
                "to_status": route.target.value,
                "route_id": route.route_id,
                "route_reason": route.reason,
                "route_predicate": route.predicate_name,
                "correlation_id": correlation_id,
                "branch_trace_id": route_trace_id,
                "branch_trace_index": route_trace_index,
                "branch_trace": route_trace,
            },
            dedup_key=None,
        )
        return saved

    def _append_route_failure_event(
        self,
        *,
        node_name: str,
        current_status: OrchestratorStatus,
        state: Mapping[str, Any],
        error: IllegalTransitionError,
    ) -> None:
        diagnostics = error.diagnostics if isinstance(error.diagnostics, Mapping) else {}
        actionable_hint = "Action: inspect route diagnostics and retry with valid transition inputs."
        message = str(error)
        if "Action:" in message:
            actionable_hint = f"Action: {message.split('Action:', maxsplit=1)[1].strip()}"
        route_trace = self._read_route_trace_from_state(state)
        route_trace_id = self._resolve_route_trace_id(state=state)
        correlation_id = self._resolve_route_correlation_id(state=state)
        route_trace_index = max(len(route_trace) - 1, 0)

        payload: dict[str, Any] = {
            "diagnostic_type": str(diagnostics.get("diagnostic_type") or "route_guard_failure"),
            "node": str(diagnostics.get("node") or diagnostics.get("trigger") or node_name),
            "current_status": str(diagnostics.get("current_status") or current_status.value),
            "attempted_target": str(diagnostics.get("attempted_target") or "<unknown>"),
            "route_id": str(diagnostics.get("route_id") or "<unknown>"),
            "route_reason": str(diagnostics.get("route_reason") or "<unknown>"),
            "route_predicate": str(diagnostics.get("predicate_name") or "<unknown>"),
            "allowed_targets": [
                str(item)
                for item in (diagnostics.get("allowed_targets") if isinstance(diagnostics.get("allowed_targets"), list) else [])
            ],
            "message": message,
            "actionable_hint": actionable_hint,
            "correlation_id": correlation_id,
            "branch_trace_id": route_trace_id,
            "branch_trace_index": route_trace_index,
            "branch_trace": route_trace,
        }

        self.state_store.append_event(
            task_id=str(state.get("task_id") or self.task_id),
            run_id=str(state.get("run_id") or self.run_id),
            step_id=state.get("current_step"),
            event_type="SYSTEM",
            severity="ERROR",
            payload=payload,
            dedup_key=None,
        )

    def _mutate_extract(self, state: dict[str, Any]) -> None:
        state.setdefault("role_lifecycle", {})
        state["role_lifecycle"]["analysis"] = "prepared"

    def _mutate_plan(self, state: dict[str, Any]) -> None:
        planning_context = self._retrieve_context_from_state(state, use_case="planning", query=None)
        state.setdefault("role_lifecycle", {})
        state["role_lifecycle"]["planning_retrieval"] = self._summarize_retrieval(planning_context)

        inherited_policy: Mapping[str, Any] | None = None
        active_step = self._active_step(state)
        if active_step is not None:
            raw_policy = active_step.get("retrieval_policy")
            if isinstance(raw_policy, Mapping):
                inherited_policy = raw_policy

        if self._should_generate_minimal_text_plan(state):
            generated_steps = [
                {field: step[field] for field in STEP_CONTRACT_FIELDS if field in step}
                for step in build_minimal_text_input_steps(
                    goal=self._normalize_optional_string(state.get("goal")) or self.goal,
                    step_id=self.step_id,
                )
            ]
            if inherited_policy is not None:
                for step in generated_steps:
                    step["retrieval_policy"] = json.loads(json.dumps(inherited_policy))
            state["steps"] = generated_steps
            if generated_steps:
                state["current_step"] = generated_steps[0]["id"]
            state["role_lifecycle"]["planner_mode"] = "text_input_minimal_v1"
            state["role_lifecycle"]["planner_step_count"] = str(len(generated_steps))
            return

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
        if self.dispatch_adapter is not None:
            self._mutate_dispatch_with_adapter(
                state=state,
                active_step=active_step,
                controller_lane=controller_lane,
                role_lifecycle=role_lifecycle,
            )

    def _mutate_dispatch_with_adapter(
        self,
        *,
        state: dict[str, Any],
        active_step: str,
        controller_lane: str,
        role_lifecycle: dict[str, Any],
    ) -> None:
        dispatch_adapter = self.dispatch_adapter
        if dispatch_adapter is None:
            return

        invocation_index = self._parse_invocation_counter(role_lifecycle.get("dispatch_invocation_count"))
        step_contract = self._active_step(state)
        correlation_id = self._resolve_dispatch_correlation_id(
            active_step=active_step,
        )
        request_payload = self._build_dispatch_request(
            state=state,
            step_contract=step_contract,
            active_step=active_step,
            controller_lane=controller_lane,
            correlation_id=correlation_id,
            invocation_index=invocation_index,
        )

        call_results: list[DispatchCallResult] = []
        next_retry_index = 0
        thread_id = self._normalize_optional_string(role_lifecycle.get("dispatch_thread_id"))
        current_result = dispatch_adapter.create(
            task_id=self.task_id,
            run_id=self.run_id,
            step_id=active_step,
            request=request_payload,
            thread_id=thread_id,
            retry_index=next_retry_index,
        )
        call_results.append(current_result)
        next_retry_index = current_result.retry_index
        thread_id = current_result.thread_id

        for resume_attempt in range(self.dispatch_max_resume_retries):
            if self._dispatch_call_succeeded(current_result):
                break
            next_retry_index += 1
            resume_request = dict(request_payload)
            resume_request["resume_attempt"] = resume_attempt + 1
            current_result = dispatch_adapter.resume(
                task_id=self.task_id,
                run_id=self.run_id,
                step_id=active_step,
                request=resume_request,
                thread_id=thread_id,
                retry_index=next_retry_index,
            )
            call_results.append(current_result)
            next_retry_index = current_result.retry_index
            thread_id = current_result.thread_id

        for rework_attempt in range(self.dispatch_max_rework_attempts):
            if self._dispatch_call_succeeded(current_result):
                break
            next_retry_index += 1
            rework_request = dict(request_payload)
            rework_request["rework_attempt"] = rework_attempt + 1
            current_result = dispatch_adapter.rework(
                task_id=self.task_id,
                run_id=self.run_id,
                step_id=active_step,
                request=rework_request,
                thread_id=thread_id,
                retry_index=next_retry_index,
                rework_context=self._build_rework_context(call_results),
            )
            call_results.append(current_result)
            next_retry_index = current_result.retry_index
            thread_id = current_result.thread_id

        call_entries = [self._dispatch_call_entry(result) for result in call_results]
        call_sequence = ",".join(entry["action"] for entry in call_entries) or "create"

        role_lifecycle["dispatch_invocation_count"] = str(invocation_index + 1)
        role_lifecycle["dispatch_call_sequence"] = call_sequence
        role_lifecycle["dispatch_artifact_count"] = str(len(call_entries))
        role_lifecycle["dispatch_last_status"] = current_result.status or "unknown"
        role_lifecycle["dispatch_last_action"] = current_result.action or "create"
        role_lifecycle["dispatch_last_retry_index"] = str(current_result.retry_index)
        role_lifecycle["dispatch_thread_id"] = current_result.thread_id
        role_lifecycle["dispatch_correlation_id"] = current_result.correlation_id

        self.state_store.append_event(
            task_id=self.task_id,
            run_id=self.run_id,
            step_id=active_step,
            event_type="SYSTEM",
            severity="INFO",
            payload={
                "node": "dispatch",
                "invocation_index": invocation_index,
                "controller_lane": controller_lane,
                "correlation_id": current_result.correlation_id,
                "thread_id": current_result.thread_id,
                "call_count": len(call_entries),
                "max_resume_retries": self.dispatch_max_resume_retries,
                "max_rework_attempts": self.dispatch_max_rework_attempts,
                "calls": call_entries,
            },
            dedup_key=(
                f"dispatch-invocation:{self.task_id}:{self.run_id}:{active_step}:{invocation_index}"
            ),
        )

    def _build_dispatch_request(
        self,
        *,
        state: Mapping[str, Any],
        step_contract: Mapping[str, Any] | None,
        active_step: str,
        controller_lane: str,
        correlation_id: str,
        invocation_index: int,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "task_kind": "step",
            "task_id": self.task_id,
            "run_id": self.run_id,
            "step_id": active_step,
            "goal": self._normalize_optional_string(state.get("goal")) or self.goal,
            "controller_lane": controller_lane,
            "correlation_id": correlation_id,
            "invocation_index": invocation_index,
        }
        if step_contract is None:
            return request

        title = self._normalize_optional_string(step_contract.get("title"))
        if title is not None:
            request["step_title"] = title
        raw_acceptance = step_contract.get("acceptance_criteria")
        acceptance = [
            item
            for item in (raw_acceptance if isinstance(raw_acceptance, list) else [])
            if isinstance(item, str) and item.strip()
        ]
        if acceptance:
            request["acceptance_criteria"] = acceptance
        raw_expected_outputs = step_contract.get("expected_outputs")
        expected_outputs = [
            item
            for item in (raw_expected_outputs if isinstance(raw_expected_outputs, list) else [])
            if isinstance(item, str) and item.strip()
        ]
        if expected_outputs:
            request["expected_outputs"] = expected_outputs
        return request

    def _dispatch_call_entry(self, result: DispatchCallResult) -> dict[str, Any]:
        entry = {
            "action": result.action,
            "status": result.status,
            "retry_index": result.retry_index,
            "thread_id": result.thread_id,
            "correlation_id": result.correlation_id,
            "artifacts": result.artifacts.normalized_paths(),
        }
        parsed = result.parsed_output
        if isinstance(parsed, Mapping):
            llm_invoked = parsed.get("llm_invoked")
            if isinstance(llm_invoked, bool):
                entry["llm_invoked"] = llm_invoked
            execution_mode = parsed.get("execution_mode")
            if isinstance(execution_mode, str) and execution_mode.strip():
                entry["execution_mode"] = execution_mode.strip()
        return entry

    def _build_rework_context(self, call_results: list[DispatchCallResult]) -> dict[str, Any]:
        failed_calls = [
            {
                "action": result.action,
                "status": result.status,
                "retry_index": result.retry_index,
                "parsed_output": json.loads(json.dumps(result.parsed_output)),
            }
            for result in call_results
            if not self._dispatch_call_succeeded(result)
        ]
        return {
            "reason": "dispatch_retry_exhausted",
            "max_resume_retries": self.dispatch_max_resume_retries,
            "max_rework_attempts": self.dispatch_max_rework_attempts,
            "failed_calls": failed_calls,
        }

    def _dispatch_call_succeeded(self, result: DispatchCallResult) -> bool:
        status = result.status
        return isinstance(status, str) and status.strip().lower() == "success"

    def _resolve_dispatch_correlation_id(
        self,
        *,
        active_step: str,
    ) -> str:
        return f"corr:{self.task_id}:{self.run_id}:{active_step}"

    def _resolve_route_trace_id(self, *, state: Mapping[str, Any]) -> str:
        active_step = self._normalize_optional_string(state.get("current_step")) or self.step_id
        return f"trace:{self.task_id}:{self.run_id}:{active_step}"

    def _resolve_route_correlation_id(self, *, state: Mapping[str, Any]) -> str | None:
        role_lifecycle = state.get("role_lifecycle")
        if isinstance(role_lifecycle, Mapping):
            dispatch_correlation_id = self._normalize_optional_string(
                role_lifecycle.get("dispatch_correlation_id")
            )
            if dispatch_correlation_id is not None:
                return dispatch_correlation_id

            route_correlation_id = self._normalize_optional_string(
                role_lifecycle.get("route:correlation_id")
            )
            if route_correlation_id is not None:
                return route_correlation_id

        active_step = self._normalize_optional_string(state.get("current_step")) or self.step_id
        return self._resolve_dispatch_correlation_id(active_step=active_step)

    def _append_route_trace(
        self,
        *,
        role_lifecycle: dict[str, Any],
        route_id: str,
    ) -> list[str]:
        existing_trace = self._read_route_trace(
            role_lifecycle.get("route:trace"),
        )
        existing_trace.append(route_id)
        role_lifecycle["route:trace"] = json.dumps(
            existing_trace,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return existing_trace

    def _read_route_trace_from_state(self, state: Mapping[str, Any]) -> list[str]:
        role_lifecycle = state.get("role_lifecycle")
        if not isinstance(role_lifecycle, Mapping):
            return []
        return self._read_route_trace(role_lifecycle.get("route:trace"))

    def _read_route_trace(self, value: Any) -> list[str]:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return []

            try:
                parsed = json.loads(normalized)
            except json.JSONDecodeError:
                parsed = None

            if isinstance(parsed, list):
                return [
                    item.strip()
                    for item in parsed
                    if isinstance(item, str) and item.strip()
                ]

            return [
                item.strip()
                for item in normalized.split(",")
                if item.strip()
            ]

        if isinstance(value, list):
            return [
                item.strip()
                for item in value
                if isinstance(item, str) and item.strip()
            ]

        return []

    def _parse_invocation_counter(self, value: Any) -> int:
        if isinstance(value, int):
            return value if value >= 0 else 0
        if not isinstance(value, str):
            return 0
        normalized = value.strip()
        if not normalized:
            return 0
        try:
            parsed = int(normalized)
        except ValueError:
            return 0
        return parsed if parsed >= 0 else 0

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

    def _normalize_non_negative_int(self, value: Any, *, name: str) -> int:
        if not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        if value < 0:
            raise ValueError(f"{name} must be >= 0")
        return value

    def _should_generate_minimal_text_plan(self, state: Mapping[str, Any]) -> bool:
        raw_steps = state.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            return True

        mapping_steps = [item for item in raw_steps if isinstance(item, Mapping)]
        if not mapping_steps:
            return True

        if len(mapping_steps) in (2, 3):
            return False

        first_step = mapping_steps[0]
        planner_source = self._normalize_optional_string(first_step.get("planner_source"))
        return planner_source == "bootstrap_default"
