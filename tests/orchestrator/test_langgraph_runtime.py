from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from contracts.validator import validate_payload
from orchestrator.langgraph_runtime import LangGraphOrchestratorRuntime
from orchestrator.state_machine import IllegalTransitionError
from state.store import StateStore


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
