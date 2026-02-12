from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from artifacts.dispatch_artifacts import DispatchArtifactStore
from dispatch.shim_adapter import DispatchError, ShimDispatchAdapter
from orchestrator.runtime import OrchestratorRuntime
from state.relay_policy import RelayModePolicy, RelayPolicyError
from state.store import StateStore


class ObserverRelayBoundaryTests(unittest.TestCase):
    def _relay_context(self) -> dict[str, object]:
        return {
            "goal": "Ship relay-only boundary",
            "constraints": ["Do not rename CLI arguments", "Keep schema_version=1.0.0"],
            "latest_instruction": "Implement DKT-019 boundary enforcement",
            "current_blockers": ["Need deterministic deny guardrails"],
            "controller_route_summary": {
                "task_id": "DKT-019",
                "run_id": "DKT-019_RUN",
                "active_lane": "controller",
                "active_step": "S1",
                "next_action": "dispatch-subagent",
            },
        }

    def _new_runtime(self, root: Path) -> OrchestratorRuntime:
        return OrchestratorRuntime(
            task_id="DKT-019",
            run_id="DKT-019_RUN",
            goal="Enforce observer relay boundary",
            state_store=StateStore(root / "state"),
            step_id="S1",
            relay_policy=RelayModePolicy(relay_mode_enabled=True),
        )

    def test_relay_mode_allows_forward_observe_and_visualize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._new_runtime(Path(tmp))
            relay_context = self._relay_context()

            forwarded = runtime.relay_forward(
                message="forward user instruction to controller",
                relay_context=relay_context,
            )
            observed = runtime.relay_observe(
                snapshot={"status": "RUNNING"},
                relay_context=relay_context,
            )
            visualized = runtime.relay_visualize(
                snapshot={"status": "FREEZE", "current_step": "S1"},
                relay_context=relay_context,
            )

            for payload, action in (
                (forwarded, "forward"),
                (observed, "observe"),
                (visualized, "visualize"),
            ):
                with self.subTest(action=action):
                    self.assertEqual(payload["mode"], "relay")
                    self.assertEqual(payload["action"], action)
                    self.assertEqual(payload["relay_context"], relay_context)

    def test_relay_mode_denies_orchestrator_execution_actions_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._new_runtime(Path(tmp))

            with self.assertRaises(RelayPolicyError) as ctx:
                runtime.dispatch()

            self.assertEqual(
                str(ctx.exception),
                "relay mode blocks execution action 'orchestrator.dispatch'; allowed relay actions: forward, observe, visualize",
            )

    def test_relay_mode_denies_shim_dispatch_actions_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = ShimDispatchAdapter(
                shim_path="/usr/local/bin/daokit-shim",
                artifact_store=DispatchArtifactStore(root / "artifacts"),
                relay_policy=RelayModePolicy(relay_mode_enabled=True),
            )

            with self.assertRaises(DispatchError) as create_ctx:
                adapter.create(
                    task_id="DKT-019",
                    run_id="DKT-019_RUN",
                    step_id="S1",
                    request={"task_kind": "step"},
                    dry_run=True,
                )
            self.assertEqual(
                str(create_ctx.exception),
                "relay mode blocks execution action 'dispatch.create'; allowed relay actions: forward, observe, visualize",
            )

            with self.assertRaises(DispatchError) as resume_ctx:
                adapter.resume(
                    task_id="DKT-019",
                    run_id="DKT-019_RUN",
                    step_id="S1",
                    thread_id="thread-controller",
                    request={"resume": True},
                    dry_run=True,
                )
            self.assertEqual(
                str(resume_ctx.exception),
                "relay mode blocks execution action 'dispatch.resume'; allowed relay actions: forward, observe, visualize",
            )

            with self.assertRaises(DispatchError) as rework_ctx:
                adapter.rework(
                    task_id="DKT-019",
                    run_id="DKT-019_RUN",
                    step_id="S1",
                    thread_id="thread-controller",
                    request={"retry": "rework"},
                    dry_run=True,
                )
            self.assertEqual(
                str(rework_ctx.exception),
                "relay mode blocks execution action 'dispatch.rework'; allowed relay actions: forward, observe, visualize",
            )

    def test_relay_context_requires_all_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._new_runtime(Path(tmp))

            with self.assertRaises(RelayPolicyError) as ctx:
                runtime.relay_forward(
                    message="forward this",
                    relay_context={"goal": "missing fields"},
                )

            self.assertEqual(
                str(ctx.exception),
                "relay context missing required fields: constraints, controller_route_summary, current_blockers, latest_instruction",
            )

    def test_non_relay_mode_accepts_normalized_codex_status_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_runner(command: list[str], payload: str) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(
                    args=command,
                    returncode=0,
                    stdout='{"status":"done"}',
                    stderr="",
                )

            adapter = ShimDispatchAdapter(
                shim_path="/usr/local/bin/daokit-shim",
                artifact_store=DispatchArtifactStore(root / "artifacts"),
                command_runner=fake_runner,
                relay_policy=RelayModePolicy(relay_mode_enabled=False),
            )

            result = adapter.create(
                task_id="DKT-034",
                run_id="DKT-034_RUN",
                step_id="S1",
                request={"task_kind": "step"},
                dry_run=False,
            )

            self.assertEqual(result.status, "success")


if __name__ == "__main__":
    unittest.main()
