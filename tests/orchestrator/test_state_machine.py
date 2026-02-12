from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from orchestrator.runtime import OrchestratorRuntime
from orchestrator.state_machine import IllegalTransitionError
from state.store import StateStore


class OrchestratorStateMachineTests(unittest.TestCase):
    def _new_runtime(self, root: Path, run_id: str = "RUN-001") -> OrchestratorRuntime:
        store = StateStore(root / "state")
        return OrchestratorRuntime(
            task_id="DKT-003",
            run_id=run_id,
            goal="Implement orchestrator state machine",
            state_store=store,
            step_id="S1",
        )

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
