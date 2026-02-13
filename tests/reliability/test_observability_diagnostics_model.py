from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from contracts.diagnostics_contracts import (
    DiagnosticCorrelationRef,
    HeartbeatFreshnessDiagnostic,
    LeaseTransitionDiagnostic,
    OperatorTimelineEntry,
    OperatorTimelineView,
    ReliabilityDiagnosticsReport,
    TakeoverDiagnostic,
)
from reliability.diagnostics import (
    build_reliability_diagnostics_report,
    emit_reliability_diagnostics,
    emit_reliability_diagnostics_from_state_store,
)
from state.store import StateStore


def _dt(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


class ObservabilityDiagnosticsModelTests(unittest.TestCase):
    def test_report_contract_serialization_is_machine_friendly(self) -> None:
        correlation = DiagnosticCorrelationRef(
            task_id="DKT-048",
            run_id="RUN-048",
            step_id="S1",
            event_id="evt-001",
            event_type="HEARTBEAT_STALE",
            occurred_at="2026-02-13T00:00:00+00:00",
        )
        report = ReliabilityDiagnosticsReport(
            schema_version="1.0.0",
            runtime_policy="LANGGRAPH_ONLY",
            task_id="DKT-048",
            run_id="RUN-048",
            generated_at="2026-02-13T00:00:00+00:00",
            heartbeat=HeartbeatFreshnessDiagnostic(
                status="STALE",
                reason_code="NO_OUTPUT_20M",
                observed_at="2026-02-13T00:00:00+00:00",
                last_signal_at="2026-02-12T23:30:00+00:00",
                silence_seconds=1800,
                warning_after_seconds=900,
                stale_after_seconds=1200,
                correlation=correlation,
            ),
            lease_transitions=(
                LeaseTransitionDiagnostic(
                    transition_kind="SNAPSHOT",
                    from_status=None,
                    to_status="ACTIVE",
                    reason_code="LEASE_ACTIVE_SNAPSHOT",
                    lease_token="lease_a",
                    lane="controller",
                    thread_id="thread-main",
                    pid=1001,
                    transition_at="2026-02-12T23:59:00+00:00",
                    correlation=correlation,
                ),
            ),
            takeover=TakeoverDiagnostic(
                trigger_reason_code="HEARTBEAT_STALE",
                lease_reason_code="VALID_ACTIVE_LEASE",
                heartbeat_status="STALE",
                decision_at="2026-02-12T23:59:30+00:00",
                takeover_at="2026-02-12T23:59:40+00:00",
                decision_latency_seconds=10,
                adopted_step_ids=("S1",),
                failed_step_ids=("S2",),
                correlation=correlation,
            ),
            timeline=OperatorTimelineView(
                schema_version="1.0.0",
                task_id="DKT-048",
                run_id="RUN-048",
                generated_at="2026-02-13T00:00:00+00:00",
                total_entries=1,
                stale_heartbeat_events=1,
                lease_transition_events=0,
                takeover_events=0,
                entries=(
                    OperatorTimelineEntry(
                        occurred_at="2026-02-12T23:59:40+00:00",
                        category="TAKEOVER",
                        event_type="LEASE_TAKEOVER",
                        severity="INFO",
                        reason_code="HEARTBEAT_STALE",
                        summary="Lease takeover executed",
                        correlation=correlation,
                        payload={"adopted_step_ids": ["S1"], "failed_step_ids": ["S2"]},
                    ),
                ),
            ),
        )

        payload = report.to_dict()
        self.assertEqual(payload["schema_version"], "1.0.0")
        self.assertEqual(payload["runtime_policy"], "LANGGRAPH_ONLY")
        self.assertEqual(payload["heartbeat"]["status"], "STALE")
        self.assertEqual(payload["takeover"]["decision_latency_seconds"], 10)
        self.assertEqual(payload["timeline"]["entries"][0]["correlation"]["task_id"], "DKT-048")
        self.assertEqual(
            payload["timeline"]["entries"][0]["payload"]["adopted_step_ids"],
            ["S1"],
        )

    def test_builder_computes_takeover_timing_and_correlations(self) -> None:
        generated_at = _dt("2026-02-13T00:00:00+00:00")
        report = build_reliability_diagnostics_report(
            task_id="DKT-048",
            run_id="RUN-048",
            heartbeat_status={
                "status": "STALE",
                "reason_code": "NO_OUTPUT_20M",
                "last_heartbeat_at": "2026-02-12T23:30:00+00:00",
                "warning_after_seconds": 900,
                "stale_after_seconds": 1200,
            },
            leases=[
                {
                    "task_id": "DKT-048",
                    "run_id": "RUN-048",
                    "step_id": "S1",
                    "lane": "controller",
                    "status": "ACTIVE",
                    "lease_token": "lease_a",
                    "thread_id": "thread-main",
                    "pid": 1001,
                    "created_at": "2026-02-12T23:00:00+00:00",
                    "updated_at": "2026-02-12T23:59:00+00:00",
                },
                {
                    "task_id": "DKT-048",
                    "run_id": "RUN-048",
                    "step_id": "S2",
                    "lane": "worker-1",
                    "status": "EXPIRED",
                    "lease_token": "lease_b",
                    "thread_id": "thread-main",
                    "pid": 1002,
                    "created_at": "2026-02-12T23:10:00+00:00",
                    "updated_at": "2026-02-12T23:58:00+00:00",
                },
            ],
            events=[
                {
                    "event_id": "evt_decide",
                    "task_id": "DKT-048",
                    "run_id": "RUN-048",
                    "step_id": "S1",
                    "event_type": "HEARTBEAT_STALE",
                    "severity": "WARN",
                    "timestamp": "2026-02-12T23:59:30+00:00",
                    "payload": {
                        "stage": "decide",
                        "decision_action": "TAKEOVER",
                        "decision_reason_code": "HEARTBEAT_STALE",
                        "heartbeat_status": "STALE",
                        "lease_reason_code": "VALID_ACTIVE_LEASE",
                        "takeover_required": True,
                        "decided_at": "2026-02-12T23:59:30+00:00",
                    },
                },
                {
                    "event_id": "evt_takeover",
                    "task_id": "DKT-048",
                    "run_id": "RUN-048",
                    "step_id": None,
                    "event_type": "LEASE_TAKEOVER",
                    "severity": "INFO",
                    "timestamp": "2026-02-12T23:59:40+00:00",
                    "payload": {
                        "takeover_at": "2026-02-12T23:59:40+00:00",
                        "reason_code": "HEARTBEAT_STALE",
                        "adopted_step_ids": ["S1"],
                        "failed_step_ids": ["S2"],
                    },
                },
                {
                    "event_id": "evt_adopted",
                    "task_id": "DKT-048",
                    "run_id": "RUN-048",
                    "step_id": "S1",
                    "event_type": "SYSTEM",
                    "severity": "INFO",
                    "timestamp": "2026-02-12T23:59:41+00:00",
                    "payload": {
                        "operation": "LEASE_ADOPTED",
                        "reason_code": "VALID_UNEXPIRED_LEASE",
                        "takeover_at": "2026-02-12T23:59:40+00:00",
                    },
                },
                {
                    "event_id": "evt_failed",
                    "task_id": "DKT-048",
                    "run_id": "RUN-048",
                    "step_id": "S2",
                    "event_type": "STEP_FAILED",
                    "severity": "ERROR",
                    "timestamp": "2026-02-12T23:59:42+00:00",
                    "payload": {
                        "reason_code": "LEASE_NOT_ADOPTED",
                        "takeover_at": "2026-02-12T23:59:40+00:00",
                    },
                },
                {
                    "event_id": "evt_other_run",
                    "task_id": "DKT-048",
                    "run_id": "RUN-OTHER",
                    "step_id": "S9",
                    "event_type": "LEASE_TAKEOVER",
                    "severity": "INFO",
                    "timestamp": "2026-02-12T23:59:45+00:00",
                    "payload": {"reason_code": "SHOULD_NOT_APPEAR"},
                },
            ],
            generated_at=generated_at,
        )
        payload = report.to_dict()

        self.assertEqual(payload["runtime_policy"], "LANGGRAPH_ONLY")
        self.assertEqual(payload["heartbeat"]["silence_seconds"], 1800)
        self.assertEqual(payload["takeover"]["trigger_reason_code"], "HEARTBEAT_STALE")
        self.assertEqual(payload["takeover"]["decision_latency_seconds"], 10)
        self.assertEqual(payload["takeover"]["correlation"]["run_id"], "RUN-048")
        self.assertEqual(payload["takeover"]["adopted_step_ids"], ["S1"])
        self.assertEqual(payload["takeover"]["failed_step_ids"], ["S2"])

        timeline_entries = payload["timeline"]["entries"]
        self.assertTrue(len(timeline_entries) >= 4)
        self.assertEqual(
            [item["occurred_at"] for item in timeline_entries],
            sorted(item["occurred_at"] for item in timeline_entries),
        )
        self.assertTrue(
            all(item["correlation"]["run_id"] == "RUN-048" for item in timeline_entries)
        )
        self.assertTrue(
            all(item["event_type"] != "LEASE_TAKEOVER" or item["reason_code"] != "SHOULD_NOT_APPEAR" for item in timeline_entries)
        )
        self.assertTrue(
            any(item["reason_code"] == "LEASE_NOT_ADOPTED" for item in timeline_entries)
        )
        self.assertTrue(
            any(
                transition["reason_code"] == "LEASE_ACTIVE_SNAPSHOT"
                for transition in payload["lease_transitions"]
            )
        )

    def test_emitter_validation_detects_missing_stale_and_takeover_signals(self) -> None:
        emission = emit_reliability_diagnostics(
            task_id="DKT-049",
            run_id="RUN-049",
            heartbeat_status={
                "status": "STALE",
                "reason_code": "NO_OUTPUT_20M",
                "warning_after_seconds": 900,
                "stale_after_seconds": 1200,
            },
            leases=[],
            events=[
                {
                    "event_id": "evt_decide_only",
                    "task_id": "DKT-049",
                    "run_id": "RUN-049",
                    "step_id": "S1",
                    "event_type": "SYSTEM",
                    "severity": "WARN",
                    "timestamp": "2026-02-13T00:00:00+00:00",
                    "payload": {
                        "stage": "decide",
                        "decision_action": "TAKEOVER",
                        "decision_reason_code": "HEARTBEAT_STALE",
                        "heartbeat_status": "STALE",
                        "lease_reason_code": "VALID_ACTIVE_LEASE",
                        "takeover_required": True,
                        "decided_at": "2026-02-13T00:00:00+00:00",
                    },
                }
            ],
            generated_at=_dt("2026-02-13T00:00:30+00:00"),
        )
        payload = emission.to_dict()
        issue_codes = [item["code"] for item in payload["validation"]["issues"]]

        self.assertEqual(payload["validation"]["status"], "FAIL")
        self.assertIn("MISSING_HEARTBEAT_STALE_SIGNAL", issue_codes)
        self.assertIn("MISSING_TAKEOVER_EVENT", issue_codes)

    def test_emitter_validation_detects_inconsistent_takeover_timing(self) -> None:
        emission = emit_reliability_diagnostics(
            task_id="DKT-049",
            run_id="RUN-049",
            heartbeat_status={"status": "WARNING"},
            leases=[],
            events=[
                {
                    "event_id": "evt_decide",
                    "task_id": "DKT-049",
                    "run_id": "RUN-049",
                    "step_id": "S1",
                    "event_type": "SYSTEM",
                    "severity": "WARN",
                    "timestamp": "2026-02-13T00:00:45+00:00",
                    "payload": {
                        "stage": "decide",
                        "decision_action": "TAKEOVER",
                        "decision_reason_code": "INVALID_LEASE_EXPIRED_CONTROLLER_LEASE",
                        "heartbeat_status": "WARNING",
                        "lease_reason_code": "EXPIRED_CONTROLLER_LEASE",
                        "takeover_required": True,
                        "decided_at": "2026-02-13T00:00:45+00:00",
                    },
                },
                {
                    "event_id": "evt_takeover",
                    "task_id": "DKT-049",
                    "run_id": "RUN-049",
                    "step_id": None,
                    "event_type": "LEASE_TAKEOVER",
                    "severity": "INFO",
                    "timestamp": "2026-02-13T00:00:40+00:00",
                    "payload": {
                        "takeover_at": "2026-02-13T00:00:40+00:00",
                        "reason_code": "INVALID_LEASE_EXPIRED_CONTROLLER_LEASE",
                        "adopted_step_ids": [],
                        "failed_step_ids": [],
                    },
                },
            ],
            generated_at=_dt("2026-02-13T00:01:00+00:00"),
        )
        payload = emission.to_dict()
        issue_codes = [item["code"] for item in payload["validation"]["issues"]]

        self.assertIn("INCONSISTENT_TAKEOVER_TIMING", issue_codes)
        self.assertEqual(payload["validation"]["status"], "FAIL")

    def test_state_store_emitter_preserves_correlation_and_timing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            state_root = repo_root / "state"
            state_store = StateStore(state_root)

            state_store.save_heartbeat_status(
                {
                    "schema_version": "1.0.0",
                    "status": "STALE",
                    "reason_code": "NO_OUTPUT_20M",
                    "last_heartbeat_at": "2026-02-12T23:40:00+00:00",
                    "warning_after_seconds": 900,
                    "stale_after_seconds": 1200,
                }
            )
            (state_root / "process_leases.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "leases": [
                            {
                                "task_id": "DKT-049",
                                "run_id": "RUN-049",
                                "step_id": "S1",
                                "lane": "controller",
                                "status": "ACTIVE",
                                "lease_token": "lease_1",
                                "thread_id": "thread-main",
                                "pid": 101,
                                "created_at": "2026-02-12T23:00:00+00:00",
                                "updated_at": "2026-02-12T23:59:00+00:00",
                                "expiry": "2026-02-13T00:20:00+00:00",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            _ = state_store.append_event(
                task_id="DKT-049",
                run_id="RUN-049",
                step_id="S1",
                event_type="HEARTBEAT_STALE",
                severity="WARN",
                payload={
                    "stage": "decide",
                    "decision_action": "TAKEOVER",
                    "decision_reason_code": "HEARTBEAT_STALE",
                    "heartbeat_status": "STALE",
                    "lease_reason_code": "VALID_ACTIVE_LEASE",
                    "takeover_required": True,
                    "decided_at": "2026-02-12T23:59:30+00:00",
                },
            )
            takeover_event = state_store.append_event(
                task_id="DKT-049",
                run_id="RUN-049",
                step_id=None,
                event_type="LEASE_TAKEOVER",
                severity="INFO",
                payload={
                    "takeover_at": "2026-02-12T23:59:40+00:00",
                    "reason_code": "HEARTBEAT_STALE",
                    "adopted_step_ids": ["S1"],
                    "failed_step_ids": [],
                },
            )
            _ = state_store.append_event(
                task_id="DKT-049",
                run_id="RUN-049",
                step_id="S1",
                event_type="SYSTEM",
                severity="INFO",
                payload={
                    "operation": "LEASE_ADOPTED",
                    "reason_code": "VALID_UNEXPIRED_LEASE",
                    "takeover_at": "2026-02-12T23:59:40+00:00",
                },
            )

            emission = emit_reliability_diagnostics_from_state_store(
                task_id="DKT-049",
                run_id="RUN-049",
                state_store=state_store,
                generated_at=_dt("2026-02-13T00:00:00+00:00"),
            )

        payload = emission.to_dict()
        self.assertEqual(payload["validation"]["status"], "PASS")
        self.assertEqual(payload["validation"]["issue_count"], 0)
        self.assertEqual(payload["report"]["takeover"]["decision_latency_seconds"], 10)
        self.assertEqual(
            payload["report"]["takeover"]["correlation"]["event_id"],
            takeover_event["event_id"],
        )
        self.assertEqual(payload["report"]["takeover"]["correlation"]["run_id"], "RUN-049")
        self.assertEqual(payload["report"]["heartbeat"]["correlation"]["run_id"], "RUN-049")


if __name__ == "__main__":
    unittest.main()
