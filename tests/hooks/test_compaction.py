from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from hooks.compaction import compact_observer_relay_context
from hooks.handoff import CoreRotationHandoffHooks
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


def _ledger() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "task_id": "DKT-022",
        "run_id": "RUN-022",
        "goal": "Implement compaction keep/drop policy",
        "status": "EXECUTE",
        "current_step": "S1",
        "steps": [_step("S1"), _step("S2")],
        "role_lifecycle": {
            "orchestrator": "running",
            "step:S1": "running",
            "step:S2": "pending",
        },
        "succession": {"enabled": True, "last_takeover_at": None},
        "updated_at": "2026-02-12T07:02:08+00:00",
    }


def _relay_context() -> dict[str, object]:
    return {
        "goal": "Keep observer relay context compact and deterministic",
        "constraints": [
            "Do not rename CLI arguments",
            "Keep schema_version=1.0.0 semantics",
        ],
        "latest_instruction": "Implement DKT-022 compaction keep/drop policy",
        "current_blockers": ["Need deterministic noise pruning"],
        "controller_route_summary": {
            "task_id": "DKT-022",
            "run_id": "RUN-022",
            "active_lane": "controller",
            "active_step": "S1",
            "next_action": "verify",
        },
        "transient_note": "this should be dropped",
    }


class RelayCompactionPolicyTests(unittest.TestCase):
    def test_keep_drop_policy_preserves_required_fields_and_prunes_noise(self) -> None:
        ledger = _ledger()
        context = {
            "relay_context": _relay_context(),
            "execution_logs": [
                {"step_id": "S1", "status": "completed", "message": "old completion"},
                {"step_id": "S1", "status": "running", "message": "active execution"},
                {"step_id": "S1", "status": "running", "message": "active execution"},
            ],
            "status_reports": [
                {"event_type": "STATUS", "step_id": "S1", "status": "RUNNING"},
                {"event_type": "STATUS", "step_id": "S1", "status": "RUNNING"},
                {"event_type": "STATUS", "step_id": "S2", "status": "PENDING"},
            ],
            "failure_noise": [
                {
                    "event_type": "SYSTEM",
                    "step_id": "S1",
                    "reason_code": "OLD_FAILURE",
                    "resolved": True,
                    "message": "resolved historical failure",
                },
                {
                    "event_type": "SYSTEM",
                    "step_id": "S1",
                    "reason_code": "ACTIVE_FAILURE",
                    "resolved": False,
                    "message": "still actionable",
                },
                {
                    "event_type": "SYSTEM",
                    "step_id": "S1",
                    "reason_code": "ACTIVE_FAILURE",
                    "resolved": False,
                    "message": "still actionable",
                },
            ],
            "api_error_dumps": [
                "Traceback: noise dump",
                {"message": "   "},
                {"code": "E_TIMEOUT", "message": "gateway timeout"},
                {"code": "E_TIMEOUT", "message": "gateway timeout"},
            ],
        }

        compact_observer_relay_context(ledger_state=ledger, context=context)

        self.assertEqual(
            context["relay_context"],
            {
                "goal": "Keep observer relay context compact and deterministic",
                "constraints": [
                    "Do not rename CLI arguments",
                    "Keep schema_version=1.0.0 semantics",
                ],
                "latest_instruction": "Implement DKT-022 compaction keep/drop policy",
                "current_blockers": ["Need deterministic noise pruning"],
                "controller_route_summary": {
                    "task_id": "DKT-022",
                    "run_id": "RUN-022",
                    "active_lane": "controller",
                    "active_step": "S1",
                    "next_action": "verify",
                },
            },
        )
        self.assertEqual(
            context["execution_logs"],
            [{"step_id": "S1", "status": "running", "message": "active execution"}],
        )
        self.assertEqual(
            context["status_reports"],
            [
                {"event_type": "STATUS", "step_id": "S1", "status": "RUNNING"},
                {"event_type": "STATUS", "step_id": "S2", "status": "PENDING"},
            ],
        )
        self.assertEqual(
            context["failure_noise"],
            [
                {
                    "event_type": "SYSTEM",
                    "step_id": "S1",
                    "reason_code": "ACTIVE_FAILURE",
                    "resolved": False,
                    "message": "still actionable",
                }
            ],
        )
        self.assertEqual(
            context["api_error_dumps"],
            [{"code": "E_TIMEOUT", "message": "gateway timeout"}],
        )

    def test_compaction_is_idempotent_across_repeated_runs(self) -> None:
        ledger = _ledger()
        context = {
            "relay_context": _relay_context(),
            "status_reports": [
                {"event_type": "STATUS", "step_id": "S1", "status": "RUNNING"},
                {"event_type": "STATUS", "step_id": "S1", "status": "RUNNING"},
            ],
            "failure_noise": [
                {
                    "event_type": "SYSTEM",
                    "step_id": "S1",
                    "reason_code": "ACTIVE_FAILURE",
                    "resolved": False,
                    "message": "still actionable",
                },
                {
                    "event_type": "SYSTEM",
                    "step_id": "S1",
                    "reason_code": "ACTIVE_FAILURE",
                    "resolved": False,
                    "message": "still actionable",
                },
            ],
        }

        compact_observer_relay_context(ledger_state=ledger, context=context)
        first_pass = json.dumps(context, sort_keys=True)

        compact_observer_relay_context(ledger_state=ledger, context=context)
        second_pass = json.dumps(context, sort_keys=True)

        self.assertEqual(first_pass, second_pass)

    def test_pre_compact_hook_runs_compaction_before_writing_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_path = Path(tmp) / "handoff_package.json"
            hooks = CoreRotationHandoffHooks(
                handoff_store=HandoffPackageStore(package_path=package_path)
            )
            ledger = _ledger()
            context = {
                "relay_context": _relay_context(),
                "evidence_paths": [
                    "reports/S1/verification.log",
                    "api_error_dump/raw.log",
                    "reports/S1/verification.log",
                    "",
                    "reports/S1/report.md",
                ],
            }

            hooks.on_pre_compact(ledger_state=ledger, context=context)
            package = hooks.handoff_store.load_package()

            self.assertIsNotNone(package)
            self.assertEqual(
                package["evidence_paths"],
                [
                    "reports/S1/verification.log",
                    "reports/S1/report.md",
                ],
            )
            self.assertEqual(
                context["relay_context"]["latest_instruction"],
                "Implement DKT-022 compaction keep/drop policy",
            )


if __name__ == "__main__":
    unittest.main()
