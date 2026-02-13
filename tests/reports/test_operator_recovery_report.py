from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from reports.operator_recovery import (
    build_and_persist_operator_recovery_report,
    build_operator_recovery_payload,
    persist_operator_recovery_report,
)
from state.store import StateStore


class OperatorRecoveryReportTests(unittest.TestCase):
    def setUp(self) -> None:  # noqa: N802
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.state_root = self.root / "state"
        self.state_store = StateStore(self.state_root)

        # Seed minimal pipeline state
        state = self.state_store.load_state()
        state.update({
            "schema_version": "1.0.0",
            "task_id": "DKT-050",
            "run_id": "RUN-TEST",
            "status": "RUNNING",
            "current_step": "S1",
        })
        _ = self.state_store.save_state(state, node="bootstrap", from_status=None, to_status="RUNNING")

        # Write a lease snapshot file with one ACTIVE lease
        (self.state_root / "process_leases.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "leases": [
                        {
                            "lease_token": "t",
                            "lane": "controller",
                            "thread_id": "integrated-successor-thread",
                            "pid": 1234,
                            "status": "ACTIVE",
                            "task_id": "DKT-050",
                            "run_id": "RUN-TEST",
                            "step_id": "S1",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        # Heartbeat went stale 30 minutes ago
        last_signal = datetime.now(timezone.utc) - timedelta(minutes=30)
        self.state_store.save_heartbeat_status(
            {
                "schema_version": "1.0.0",
                "status": "STALE",
                "last_heartbeat_at": last_signal.isoformat(),
                "reason_code": "NO_OUTPUT_20M",
                "warning_after_seconds": 900,
                "stale_after_seconds": 1200,
            }
        )

        # Emit a stale heartbeat event and a takeover
        _ = self.state_store.append_event(
            task_id="DKT-050",
            run_id="RUN-TEST",
            step_id="S1",
            event_type="HEARTBEAT_STALE",
            severity="WARN",
            payload={
                "reason_code": "NO_OUTPUT_20M",
            },
        )

        takeover_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        decision_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        _ = self.state_store.append_event(
            task_id="DKT-050",
            run_id="RUN-TEST",
            step_id="S1",
            event_type="LEASE_TAKEOVER",
            severity="INFO",
            payload={
                "reason_code": "INVALID_LEASE_TOKEN",
                "lease_token": "t",
                "lane": "controller",
                "thread_id": "integrated-successor-thread",
                "pid": 2222,
                "adopted_step_ids": ["S1"],
                "failed_step_ids": [],
                "takeover_at": takeover_at.isoformat(),
                "decided_at": decision_at.isoformat(),
                "lease_reason_code": "VALID_UNEXPIRED_LEASE",
                "heartbeat_status": "STALE",
            },
        )

    def tearDown(self) -> None:  # noqa: N802
        self.tmpdir.cleanup()

    def test_build_operator_recovery_payload_includes_required_sections(self) -> None:
        payload = build_operator_recovery_payload(
            task_id="DKT-050", run_id="RUN-TEST", state_root=self.state_root
        )

        # schema and policy from DKT-049 diagnostics
        self.assertEqual(payload["schema_version"], "1.0.0")
        self.assertEqual(payload["runtime_policy"], "LANGGRAPH_ONLY")

        # stale detection
        self.assertEqual(payload["stale_detection"]["heartbeat_status"], "STALE")
        self.assertIn("silence_seconds", payload["stale_detection"])

        # takeover latency section
        self.assertTrue(payload["takeover_latency"]["detected"])
        self.assertIn("decision_at", payload["takeover_latency"])  # may be None if not resolvable
        self.assertIn("takeover_at", payload["takeover_latency"])  # ISO timestamp string

        # continuity outcome present with checks
        self.assertIn(payload["continuity_outcome"]["status"], {"PASS", "REQUIRES_REVIEW"})
        self.assertIsInstance(payload["continuity_outcome"].get("continuity_checks", []), list)

        # timeline excerpt and counts
        self.assertIn("entries", payload["timeline"])
        self.assertGreaterEqual(payload["timeline"]["total_entries"], 1)

    def test_persist_operator_recovery_report_writes_json_and_markdown(self) -> None:
        payload = build_operator_recovery_payload(
            task_id="DKT-050", run_id="RUN-TEST", state_root=self.state_root
        )

        out_json = self.root / "report.json"
        out_md = self.root / "report.md"
        artifacts = persist_operator_recovery_report(
            payload=payload, output_json=out_json, output_markdown=out_md
        )

        self.assertTrue(out_json.exists(), "JSON report not written")
        self.assertTrue(out_md.exists(), "Markdown report not written")
        written = json.loads(out_json.read_text(encoding="utf-8"))
        self.assertEqual(written["task_id"], "DKT-050")
        self.assertEqual(artifacts.state_root, str(self.state_root.resolve()))

    def test_build_and_persist_operator_recovery_report_returns_evidence_pointers(self) -> None:
        out_json = self.root / "report.json"
        out_md = self.root / "report.md"
        payload, artifacts = build_and_persist_operator_recovery_report(
            task_id="DKT-050",
            run_id="RUN-TEST",
            state_root=self.state_root,
            output_json=out_json,
            output_markdown=out_md,
        )

        pointers = payload.get("evidence_pointers", {})
        self.assertEqual(pointers.get("recovery_json"), str(out_json))
        self.assertEqual(pointers.get("recovery_markdown"), str(out_md))
        # ensure pointer paths are strings to files we expect
        for key in ("pipeline_state_json", "heartbeat_status_json", "process_leases_json", "events_jsonl"):
            self.assertIsInstance(pointers.get(key), str)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

