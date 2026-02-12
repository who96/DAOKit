from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hooks.handoff import register_core_rotation_hooks
from hooks.runtime import HookPoint, HookRuntime
from reliability.handoff import HandoffPackageStore


def _step(step_id: str) -> dict[str, object]:
    return {
        "id": step_id,
        "title": f"Step {step_id}",
        "category": "implementation",
        "goal": f"Deliver {step_id}",
        "actions": ["run"],
        "acceptance_criteria": [f"{step_id}-criterion-1", f"{step_id}-criterion-2"],
        "expected_outputs": [f"{step_id}/report.md", f"{step_id}/verification.log"],
        "dependencies": [],
    }


def _ledger(
    *,
    current_step: str | None,
    lifecycle_by_step: dict[str, str],
) -> dict[str, object]:
    role_lifecycle: dict[str, str] = {"orchestrator": "running"}
    for step_id, lifecycle in lifecycle_by_step.items():
        role_lifecycle[f"step:{step_id}"] = lifecycle
    return {
        "schema_version": "1.0.0",
        "task_id": "DKT-015",
        "run_id": "RUN-015",
        "goal": "Implement core rotation handoff package",
        "status": "EXECUTE",
        "current_step": current_step,
        "steps": [_step("S1"), _step("S2"), _step("S3")],
        "role_lifecycle": role_lifecycle,
        "succession": {"enabled": True, "last_takeover_at": None},
        "updated_at": "2026-02-11T15:51:19+00:00",
    }


class CoreRotationHandoffTests(unittest.TestCase):
    def test_pre_compact_persists_handoff_package_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_path = Path(tmp) / "handoff_package.json"
            store = HandoffPackageStore(package_path=package_path)
            ledger = _ledger(
                current_step="S2",
                lifecycle_by_step={
                    "S1": "accepted",
                    "S2": "running",
                    "S3": "pending",
                },
            )

            package = store.write_package(
                ledger,
                evidence_paths=["reports/S2/report.md", "reports/S2/verification.log"],
            )
            loaded = store.load_package()

            self.assertIsNotNone(loaded)
            self.assertEqual(package["task_id"], "DKT-015")
            self.assertEqual(package["run_id"], "RUN-015")
            self.assertEqual(package["current_step"], "S2")
            self.assertIn("open_acceptance_items", package)
            self.assertIn("evidence_paths", package)
            self.assertIn("next_action", package)
            self.assertIn("package_hash", package)
            self.assertEqual(loaded, package)

    def test_rotation_resumes_correct_step_and_skips_accepted_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_path = Path(tmp) / "handoff_package.json"
            store = HandoffPackageStore(package_path=package_path)
            pre_compact_ledger = _ledger(
                current_step="S1",
                lifecycle_by_step={
                    "S1": "accepted",
                    "S2": "accepted",
                    "S3": "running",
                },
            )
            store.write_package(pre_compact_ledger)

            session_ledger = _ledger(
                current_step="S1",
                lifecycle_by_step={
                    "S1": "accepted",
                    "S2": "accepted",
                    "S3": "pending",
                },
            )
            resume = store.apply_package(session_ledger)

            self.assertEqual(resume.resume_step_id, "S3")
            self.assertEqual(session_ledger["current_step"], "S3")
            self.assertEqual(resume.skipped_step_ids, ("S1", "S2"))
            self.assertEqual(resume.resumable_step_ids, ("S3",))

    def test_pending_and_failed_steps_remain_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_path = Path(tmp) / "handoff_package.json"
            store = HandoffPackageStore(package_path=package_path)
            pre_compact_ledger = _ledger(
                current_step="S2",
                lifecycle_by_step={
                    "S1": "accepted",
                    "S2": "failed_non_adopted_lease",
                    "S3": "pending",
                },
            )
            store.write_package(pre_compact_ledger)

            session_ledger = _ledger(
                current_step="S2",
                lifecycle_by_step={
                    "S1": "accepted",
                    "S2": "failed_non_adopted_lease",
                    "S3": "pending",
                },
            )
            resume = store.apply_package(session_ledger)

            self.assertEqual(resume.resume_step_id, "S2")
            self.assertEqual(resume.resumable_step_ids, ("S2", "S3"))
            self.assertEqual(resume.skipped_step_ids, ("S1",))
            self.assertTrue(
                any(item["step_id"] == "S2" for item in resume.open_acceptance_items)
            )
            self.assertTrue(
                any(item["step_id"] == "S3" for item in resume.open_acceptance_items)
            )

    def test_hooks_chain_pre_compact_then_session_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_path = Path(tmp) / "handoff_package.json"
            runtime = HookRuntime()
            register_core_rotation_hooks(
                runtime,
                handoff_store=HandoffPackageStore(package_path=package_path),
            )

            pre_compact_ledger = _ledger(
                current_step="S2",
                lifecycle_by_step={
                    "S1": "accepted",
                    "S2": "running",
                    "S3": "pending",
                },
            )
            compact_result = runtime.run(
                hook_point=HookPoint.PRE_COMPACT.value,
                ledger_state=pre_compact_ledger,
                context={},
                idempotency_key="compact-1",
            )
            self.assertEqual(compact_result.status, "success")
            self.assertTrue(package_path.exists())

            session_ledger = _ledger(
                current_step="S1",
                lifecycle_by_step={
                    "S1": "accepted",
                    "S2": "running",
                    "S3": "pending",
                },
            )
            session_result = runtime.run(
                hook_point=HookPoint.SESSION_START.value,
                ledger_state=session_ledger,
                context={},
                idempotency_key="session-1",
            )

            self.assertEqual(session_result.status, "success")
            self.assertEqual(session_result.ledger_state["current_step"], "S2")
            lifecycle = session_result.ledger_state["role_lifecycle"]
            self.assertEqual(lifecycle["handoff_resume_step"], "S2")


if __name__ == "__main__":
    unittest.main()
