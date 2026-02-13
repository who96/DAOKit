from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence
import unittest

from artifacts.dispatch_artifacts import DispatchArtifactStore
from dispatch.shim_adapter import ShimDispatchAdapter
from orchestrator.runtime import OrchestratorRuntime
from orchestrator.state_machine import (
    IllegalTransitionError,
    OrchestratorStatus,
    resolve_conditional_route,
)
from state.store import StateStore


class _SequencedRunner:
    def __init__(self, responses: list[tuple[int, Mapping[str, Any] | str]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, command: Sequence[str], payload: str) -> subprocess.CompletedProcess[str]:
        parsed_payload = json.loads(payload)
        action = command[1] if len(command) > 1 else ""
        self.calls.append(
            {
                "command": list(command),
                "action": action,
                "payload": parsed_payload,
            }
        )
        if not self._responses:
            raise AssertionError("no scripted shim response available")
        return_code, stdout_payload = self._responses.pop(0)
        if isinstance(stdout_payload, str):
            stdout_text = stdout_payload
        else:
            stdout_text = json.dumps(stdout_payload, sort_keys=True)
        return subprocess.CompletedProcess(
            args=list(command),
            returncode=return_code,
            stdout=stdout_text,
            stderr="",
        )


class OrchestratorStateMachineTests(unittest.TestCase):
    def _new_runtime(
        self,
        root: Path,
        run_id: str = "RUN-001",
        dispatch_adapter: ShimDispatchAdapter | None = None,
        dispatch_max_resume_retries: int = 1,
        dispatch_max_rework_attempts: int = 1,
    ) -> OrchestratorRuntime:
        store = StateStore(root / "state")
        return OrchestratorRuntime(
            task_id="DKT-003",
            run_id=run_id,
            goal="Implement orchestrator state machine",
            state_store=store,
            step_id="S1",
            dispatch_adapter=dispatch_adapter,
            dispatch_max_resume_retries=dispatch_max_resume_retries,
            dispatch_max_rework_attempts=dispatch_max_rework_attempts,
        )

    def _read_events(self, runtime: OrchestratorRuntime) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for line in runtime.state_store.events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                events.append(parsed)
        return events

    def test_happy_path_runs_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._new_runtime(Path(tmp))

            final_state = runtime.run()
            snapshots = runtime.state_store.list_snapshots()
            transition_nodes = [entry.get("node") for entry in snapshots]

            self.assertEqual(final_state["status"], "DONE")
            self.assertEqual(final_state["current_step"], "S1")
            self.assertIn("bootstrap", transition_nodes)
            self.assertEqual(
                [name for name in transition_nodes if name in {"extract", "plan", "dispatch", "verify", "transition"}],
                ["extract", "plan", "dispatch", "verify", "transition"],
            )

    def test_dispatch_persists_controller_lane_ownership_in_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._new_runtime(Path(tmp))
            runtime.extract()
            runtime.plan()

            state = runtime.dispatch()
            lifecycle = state["role_lifecycle"]

            self.assertEqual(lifecycle["controller_lane"], "controller")
            self.assertEqual(lifecycle["controller_ownership"], "controller:S1")
            self.assertEqual(lifecycle["lane:controller"], "active_step:S1")
            self.assertEqual(lifecycle["step:S1"], "owned_by_lane:controller")

    def test_plan_generates_bounded_executable_steps_from_text_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = OrchestratorRuntime(
                task_id="DKT-057",
                run_id="RUN-TEXT-PLAN",
                goal="Implement minimal text-input extract-plan-dispatch-acceptance flow",
                state_store=StateStore(Path(tmp) / "state"),
                step_id="S1",
            )

            runtime.extract()
            state = runtime.plan()
            steps = [item for item in state.get("steps", []) if isinstance(item, dict)]

            self.assertGreaterEqual(len(steps), 2)
            self.assertLessEqual(len(steps), 3)
            for step in steps:
                self.assertTrue(step.get("actions"))
                self.assertTrue(step.get("acceptance_criteria"))
                self.assertTrue(step.get("expected_outputs"))

            lifecycle = state["role_lifecycle"]
            self.assertEqual(lifecycle["planner_mode"], "text_input_minimal_v1")
            self.assertEqual(int(lifecycle["planner_step_count"]), len(steps))

    def test_dispatch_routes_to_shim_create_and_persists_dispatch_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = _SequencedRunner(
                responses=[
                    (
                        0,
                        {
                            "status": "success",
                            "worker": "ready",
                        },
                    )
                ]
            )
            adapter = ShimDispatchAdapter(
                shim_path="/usr/local/bin/daokit-shim",
                artifact_store=DispatchArtifactStore(root / "dispatch-artifacts"),
                command_runner=runner,
            )
            runtime = self._new_runtime(root, dispatch_adapter=adapter)
            runtime.extract()
            runtime.plan()

            state = runtime.dispatch()
            lifecycle = state["role_lifecycle"]

            self.assertEqual([call["action"] for call in runner.calls], ["create"])
            self.assertEqual(lifecycle["dispatch_last_action"], "create")
            self.assertEqual(lifecycle["dispatch_last_status"], "success")
            self.assertEqual(lifecycle["dispatch_call_sequence"], "create")
            self.assertEqual(lifecycle["dispatch_invocation_count"], "1")

            dispatch_events = [
                event
                for event in self._read_events(runtime)
                if str(event.get("dedup_key", "")).startswith("dispatch-invocation:")
            ]
            self.assertEqual(len(dispatch_events), 1)
            payload = dispatch_events[0]["payload"]
            self.assertEqual(payload["node"], "dispatch")
            self.assertEqual(payload["call_count"], 1)
            call_entry = payload["calls"][0]
            self.assertEqual(call_entry["action"], "create")
            self.assertEqual(call_entry["status"], "success")
            self.assertTrue(Path(call_entry["artifacts"]["request"]).is_file())
            self.assertTrue(Path(call_entry["artifacts"]["output"]).is_file())
            self.assertTrue(Path(call_entry["artifacts"]["error"]).is_file())

    def test_dispatch_retry_and_rework_sequence_is_deterministic_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = _SequencedRunner(
                responses=[
                    (1, {"status": "error", "reason": "create failed"}),
                    (1, {"status": "error", "reason": "resume failed"}),
                    (0, {"status": "success", "reason": "rework fixed"}),
                ]
            )
            adapter = ShimDispatchAdapter(
                shim_path="/usr/local/bin/daokit-shim",
                artifact_store=DispatchArtifactStore(root / "dispatch-artifacts"),
                command_runner=runner,
            )
            runtime = self._new_runtime(
                root,
                dispatch_adapter=adapter,
                dispatch_max_resume_retries=1,
                dispatch_max_rework_attempts=1,
            )
            runtime.extract()
            runtime.plan()

            state = runtime.dispatch()
            lifecycle = state["role_lifecycle"]

            self.assertEqual(
                [call["action"] for call in runner.calls],
                ["create", "resume", "rework"],
            )
            retry_indices = [int(call["payload"]["retry_index"]) for call in runner.calls]
            self.assertEqual(retry_indices, [0, 1, 2])

            thread_ids = {str(call["payload"]["thread_id"]) for call in runner.calls}
            correlation_ids = {str(call["payload"]["correlation_id"]) for call in runner.calls}
            self.assertEqual(len(thread_ids), 1)
            self.assertEqual(len(correlation_ids), 1)

            self.assertEqual(lifecycle["dispatch_call_sequence"], "create,resume,rework")
            self.assertEqual(lifecycle["dispatch_last_action"], "rework")
            self.assertEqual(lifecycle["dispatch_last_status"], "success")
            self.assertEqual(lifecycle["dispatch_last_retry_index"], "2")

            dispatch_events = [
                event
                for event in self._read_events(runtime)
                if str(event.get("dedup_key", "")).startswith("dispatch-invocation:")
            ]
            self.assertEqual(len(dispatch_events), 1)
            payload = dispatch_events[0]["payload"]
            self.assertEqual(payload["call_count"], 3)
            self.assertEqual(
                [entry["action"] for entry in payload["calls"]],
                ["create", "resume", "rework"],
            )
            self.assertEqual(
                [int(entry["retry_index"]) for entry in payload["calls"]],
                [0, 1, 2],
            )
            for entry in payload["calls"]:
                self.assertTrue(Path(entry["artifacts"]["request"]).is_file())
                self.assertTrue(Path(entry["artifacts"]["output"]).is_file())
                self.assertTrue(Path(entry["artifacts"]["error"]).is_file())

    def test_transition_route_decision_is_deterministic_with_reason_metadata(self) -> None:
        failed_decision = resolve_conditional_route(
            node_name="transition",
            current=OrchestratorStatus.ACCEPT,
            state={"role_lifecycle": {"acceptance": "failed"}},
        )
        self.assertEqual(failed_decision.target, OrchestratorStatus.EXECUTE)
        self.assertEqual(failed_decision.route_id, "transition.acceptance_failed.rework")
        self.assertEqual(failed_decision.reason, "acceptance_failed_rework")
        self.assertEqual(failed_decision.predicate_name, "acceptance_failed")

        passed_decision = resolve_conditional_route(
            node_name="transition",
            current=OrchestratorStatus.ACCEPT,
            state={"role_lifecycle": {"acceptance": "passed"}},
        )
        self.assertEqual(passed_decision.target, OrchestratorStatus.DONE)
        self.assertEqual(passed_decision.route_id, "transition.acceptance_not_failed.done")
        self.assertEqual(passed_decision.reason, "acceptance_not_failed_finalize")
        self.assertEqual(passed_decision.predicate_name, "acceptance_not_failed")

    def test_undefined_route_policy_reports_actionable_diagnostics(self) -> None:
        with self.assertRaises(IllegalTransitionError) as ctx:
            resolve_conditional_route(
                node_name="undefined-node",
                current=OrchestratorStatus.PLANNING,
                state={},
            )

        message = str(ctx.exception)
        self.assertIn("Undefined conditional route policy", message)
        self.assertIn("Action:", message)

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
            self.assertIn("Route diagnostics:", message)
            self.assertIn("Action:", message)

    def test_illegal_transition_emits_route_guard_failure_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._new_runtime(Path(tmp))

            with self.assertRaises(IllegalTransitionError):
                runtime.transition()

            route_failures = [
                event
                for event in self._read_events(runtime)
                if event.get("severity") == "ERROR"
                and isinstance(event.get("payload"), dict)
                and event["payload"].get("diagnostic_type") == "route_guard_failure"
            ]

            self.assertEqual(len(route_failures), 1)
            payload = route_failures[0]["payload"]
            self.assertEqual(payload["node"], "transition")
            self.assertEqual(payload["current_status"], "PLANNING")
            self.assertEqual(payload["attempted_target"], "DONE")
            self.assertEqual(payload["route_reason"], "acceptance_not_failed_finalize")
            self.assertIn("Action:", payload["actionable_hint"])
            self.assertEqual(payload["correlation_id"], "corr:DKT-003:RUN-001:S1")
            self.assertEqual(payload["branch_trace_id"], "trace:DKT-003:RUN-001:S1")
            self.assertEqual(int(payload["branch_trace_index"]), 0)
            self.assertEqual(payload["branch_trace"], [])

    def test_state_is_recoverable_after_process_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            first_runtime = self._new_runtime(root, run_id="RUN-RECOVER")
            first_runtime.extract()
            first_runtime.plan()

            resumed_runtime = self._new_runtime(root, run_id="RUN-RECOVER")
            recovered_state = resumed_runtime.recover_state()
            final_state = resumed_runtime.run()

            self.assertEqual(recovered_state["status"], "FREEZE")
            self.assertEqual(final_state["status"], "DONE")
            self.assertEqual(final_state["run_id"], "RUN-RECOVER")


if __name__ == "__main__":
    unittest.main()
