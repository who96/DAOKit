from __future__ import annotations

import copy
import json
import unittest

from planner.compiler import PlanCompilationError, compile_plan


class StrictPlanCompilerTests(unittest.TestCase):
    def _valid_plan(self) -> dict[str, object]:
        return {
            "goal": "Ship strict compiler for dispatch",
            "dependencies": ["DKT-003"],
            "steps": [
                {
                    "id": "S1",
                    "title": "Compile plan",
                    "category": "implementation",
                    "goal": "Compile validated step contracts",
                    "actions": [
                        "Normalize incoming task payload",
                        "Validate required step fields",
                    ],
                    "acceptance_criteria": [
                        "Malformed steps are rejected",
                        "Output ids stay deterministic",
                    ],
                    "expected_outputs": [
                        "src/planner/compiler.py",
                        "tests/planner/test_compiler.py",
                    ],
                    "dependencies": ["DKT-003"],
                },
                {
                    "id": "S2",
                    "title": "Verify compiler",
                    "category": "verification",
                    "goal": "Run planner tests",
                    "actions": ["Execute planner test suite"],
                    "acceptance_criteria": ["All planner tests pass"],
                    "expected_outputs": ["verification.log"],
                    "dependencies": ["S1"],
                },
            ],
        }

    def test_compiler_rejects_missing_required_fields(self) -> None:
        payload = self._valid_plan()
        step0 = payload["steps"][0]  # type: ignore[index]
        step0.pop("goal")  # type: ignore[union-attr]

        with self.assertRaises(PlanCompilationError) as ctx:
            compile_plan(payload)

        self.assertIn("missing required field 'goal'", str(ctx.exception))

    def test_compiler_rejects_under_specified_step_lists(self) -> None:
        payload = self._valid_plan()
        payload["steps"][0]["actions"] = []  # type: ignore[index]

        with self.assertRaises(PlanCompilationError) as ctx:
            compile_plan(payload)

        self.assertIn("actions", str(ctx.exception))
        self.assertIn("at least 1", str(ctx.exception))

    def test_compiler_rejects_duplicate_step_identifiers(self) -> None:
        payload = self._valid_plan()
        payload["steps"][1]["id"] = "S1"  # type: ignore[index]

        with self.assertRaises(PlanCompilationError) as ctx:
            compile_plan(payload)

        self.assertIn("duplicate step id", str(ctx.exception))

    def test_compiler_rejects_duplicate_expected_outputs_across_steps(self) -> None:
        payload = self._valid_plan()
        payload["steps"][1]["expected_outputs"] = ["verification.log", "src/planner/compiler.py"]  # type: ignore[index]

        with self.assertRaises(PlanCompilationError) as ctx:
            compile_plan(payload)

        self.assertIn("expected output", str(ctx.exception))
        self.assertIn("multiple steps", str(ctx.exception))

    def test_compiler_rejects_dependency_cycles(self) -> None:
        payload = self._valid_plan()
        payload["steps"][0]["dependencies"] = ["S2"]  # type: ignore[index]

        with self.assertRaises(PlanCompilationError) as ctx:
            compile_plan(payload)

        self.assertIn("dependency cycle", str(ctx.exception))

    def test_compiler_rejects_unknown_dependencies(self) -> None:
        payload = self._valid_plan()
        payload["steps"][1]["dependencies"] = ["S1", "DKT-404"]  # type: ignore[index]

        with self.assertRaises(PlanCompilationError) as ctx:
            compile_plan(payload)

        self.assertIn("unknown step", str(ctx.exception))

    def test_compiler_rejects_path_alias_output_conflicts(self) -> None:
        payload = self._valid_plan()
        payload["steps"][1]["expected_outputs"] = [  # type: ignore[index]
            "verification.log",
            "./src/planner/compiler.py",
        ]

        with self.assertRaises(PlanCompilationError) as ctx:
            compile_plan(payload)

        self.assertIn("expected output conflict", str(ctx.exception))

    def test_compiler_output_is_stable_for_same_input(self) -> None:
        payload = self._valid_plan()

        first = compile_plan(copy.deepcopy(payload)).to_dispatch_payload()
        second = compile_plan(copy.deepcopy(payload)).to_dispatch_payload()

        self.assertEqual(first, second)
        self.assertEqual(first["task_id"], second["task_id"])
        self.assertEqual(first["run_id"], second["run_id"])

    def test_compiler_handles_deep_acyclic_dependency_chains(self) -> None:
        total_steps = 1200
        payload: dict[str, object] = {
            "goal": "Stress dependency topology",
            "steps": [],
        }
        steps = payload["steps"]  # type: ignore[index]
        for index in range(total_steps):
            step_id = f"S{index + 1}"
            dependencies = [] if index == total_steps - 1 else [f"S{index + 2}"]
            steps.append(  # type: ignore[union-attr]
                {
                    "id": step_id,
                    "title": step_id,
                    "category": "implementation",
                    "goal": f"Complete {step_id}",
                    "actions": [f"Run {step_id}"],
                    "acceptance_criteria": [f"{step_id} complete"],
                    "expected_outputs": [f"out/{step_id}.txt"],
                    "dependencies": dependencies,
                }
            )

        compiled = compile_plan(payload).to_dispatch_payload()
        self.assertEqual(len(compiled["steps"]), total_steps)
        self.assertEqual(compiled["steps"][0]["id"], "S1")
        self.assertEqual(compiled["steps"][-1]["id"], f"S{total_steps}")

    def test_compiler_output_is_dispatch_consumable(self) -> None:
        payload = self._valid_plan()

        compiled = compile_plan(payload).to_dispatch_payload()

        self.assertIn("task_id", compiled)
        self.assertIn("run_id", compiled)
        self.assertIn("goal", compiled)
        self.assertIn("steps", compiled)
        self.assertIn("step_index", compiled)

        self.assertEqual(compiled["steps"][0]["id"], "S1")
        self.assertEqual(compiled["step_index"]["S1"], 0)

        rendered = json.dumps(compiled, sort_keys=True)
        self.assertIn("acceptance_criteria", rendered)
        self.assertIn("expected_outputs", rendered)


if __name__ == "__main__":
    unittest.main()
