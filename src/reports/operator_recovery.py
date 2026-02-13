from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reliability.diagnostics import emit_reliability_diagnostics_from_state_store
from state.store import create_state_backend


@dataclass(frozen=True)
class OperatorRecoveryReportArtifacts:
    """Paths for operator-facing recovery evidence."""

    state_root: str
    pipeline_state_json: str
    heartbeat_status_json: str
    process_leases_json: str
    events_jsonl: str
    json_report_path: str
    markdown_report_path: str


def build_operator_recovery_payload(
    *,
    task_id: str,
    run_id: str,
    state_root: Path,
) -> dict[str, Any]:
    state_store = create_state_backend(state_root)
    emission = emit_reliability_diagnostics_from_state_store(
        task_id=task_id,
        run_id=run_id,
        state_store=state_store,
    )

    report = emission.to_dict()
    heartbeat = report["report"]["heartbeat"]
    takeover = report["report"].get("takeover")
    continuity_passed = report["validation"]["status"] == "PASS" and takeover is not None

    stale_status = (heartbeat.get("status") or "UNKNOWN").upper()
    stale_detection = {
        "heartbeat_status": stale_status,
        "reason_code": heartbeat.get("reason_code"),
        "silence_seconds": heartbeat.get("silence_seconds"),
        "warning_after_seconds": heartbeat.get("warning_after_seconds"),
        "stale_after_seconds": heartbeat.get("stale_after_seconds"),
        "stale_events_in_timeline": report["report"]["timeline"].get("stale_heartbeat_events", 0),
        "timeline_entries": report["report"]["timeline"].get("total_entries", 0),
    }

    takeover_latency = {
        "detected": takeover is not None,
        "trigger_reason_code": takeover.get("trigger_reason_code") if takeover else None,
        "lease_reason_code": takeover.get("lease_reason_code") if takeover else None,
        "decision_at": takeover.get("decision_at") if takeover else None,
        "takeover_at": takeover.get("takeover_at") if takeover else None,
        "decision_latency_seconds": takeover.get("decision_latency_seconds") if takeover else None,
        "adopted_step_ids": list(takeover.get("adopted_step_ids")) if takeover else [],
        "failed_step_ids": list(takeover.get("failed_step_ids")) if takeover else [],
    }

    continuity_outcome = {
        "status": "PASS" if continuity_passed else "REQUIRES_REVIEW",
        "validation_status": report["validation"].get("status"),
        "validation_issue_count": report["validation"].get("issue_count", 0),
        "event_count": report["evidence"].get("event_count", 0),
        "lease_count": report["evidence"].get("lease_count", 0),
        "continuity_checks": [
            {
                "name": "takeover_present",
                "passed": takeover is not None,
            },
            {
                "name": "stale_detection_emitted",
                "passed": stale_status in {"STALE", "WARNING", "CRITICAL"},
            },
            {
                "name": "validation_passed",
                "passed": report["validation"].get("status") == "PASS",
            },
        ],
    }

    timeline = report["report"]["timeline"].get("entries", [])
    timeline_excerpt = timeline[-20:] if len(timeline) > 20 else timeline

    return {
        "task_id": task_id,
        "run_id": run_id,
        "schema_version": report["schema_version"],
        "runtime_policy": report["runtime_policy"],
        "generated_at": report["generated_at"],
        "state_root": str(state_root.resolve()),
        "stale_detection": stale_detection,
        "takeover_latency": takeover_latency,
        "continuity_outcome": continuity_outcome,
        "timeline": {
            "entries": timeline_excerpt,
            "total_entries": len(timeline),
        },
        "validation": report["validation"],
    }


def _render_operator_recovery_markdown(payload: dict[str, Any]) -> str:
    stale = payload["stale_detection"]
    takeover = payload["takeover_latency"]
    continuity = payload["continuity_outcome"]
    checks = [
        f"- {item['name']}: {'PASS' if item['passed'] else 'FAIL'}"
        for item in continuity.get("continuity_checks", [])
    ]

    lines = [
        "# Operator Recovery Dashboard",
        "",
        f"- Task ID: {payload['task_id']}",
        f"- Run ID: {payload['run_id']}",
        f"- Generated At: {payload['generated_at']}",
        f"- Runtime Policy: {payload['runtime_policy']}",
        "",
        "## Stale Detection",
        f"- Status: {stale['heartbeat_status']}",
        f"- Reason: {stale.get('reason_code')}",
        f"- Silence Seconds: {stale.get('silence_seconds')}",
        f"- Warning After: {stale.get('warning_after_seconds')}",
        f"- Stale After: {stale.get('stale_after_seconds')}",
        f"- Stale Heartbeat Events: {stale.get('stale_events_in_timeline')}",
        "",
        "## Takeover Latency",
        f"- Takeover Detected: {takeover['detected']}",
        f"- Trigger Reason: {takeover.get('trigger_reason_code')}",
        f"- Lease Reason: {takeover.get('lease_reason_code')}",
        f"- Decision At: {takeover.get('decision_at')}",
        f"- Takeover At: {takeover.get('takeover_at')}",
        f"- Decision Latency (s): {takeover.get('decision_latency_seconds')}",
        f"- Adopted Steps: {', '.join(takeover.get('adopted_step_ids') or [])}",
        f"- Failed Steps: {', '.join(takeover.get('failed_step_ids') or [])}",
        "",
        "## Continuity Outcome",
        f"- Status: {continuity.get('status')}",
        f"- Validation: {continuity.get('validation_status')}",
        f"- Event Count: {continuity.get('event_count')}",
        f"- Lease Count: {continuity.get('lease_count')}",
        "- Checks:",
        *checks,
        "",
        "## Timeline Snapshot",
        "- Total Timeline Entries: {}".format(payload["timeline"]["total_entries"]),
        *["- {task_id}/{run_id} {occurred_at} {event_type} {severity}: {summary}".format(
            task_id=payload["task_id"],
            run_id=payload["run_id"],
            occurred_at=entry.get("occurred_at"),
            event_type=entry.get("event_type"),
            severity=entry.get("severity"),
            summary=entry.get("summary"),
        ) for entry in payload["timeline"].get("entries", [])],
    ]
    return "\n".join(lines) + "\n"


def persist_operator_recovery_report(
    *,
    payload: dict[str, Any],
    output_json: Path,
    output_markdown: Path,
) -> OperatorRecoveryReportArtifacts:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(__import__("json").dumps(payload, indent=2) + "\n", encoding="utf-8")
    output_markdown.write_text(_render_operator_recovery_markdown(payload), encoding="utf-8")

    state_root = Path(payload.get("state_root", Path(".").resolve()))
    return OperatorRecoveryReportArtifacts(
        state_root=str(state_root),
        pipeline_state_json=str(state_root / "pipeline_state.json"),
        heartbeat_status_json=str(state_root / "heartbeat_status.json"),
        process_leases_json=str(state_root / "process_leases.json"),
        events_jsonl=str(state_root / "events.jsonl"),
        json_report_path=str(output_json),
        markdown_report_path=str(output_markdown),
    )


def build_and_persist_operator_recovery_report(
    *,
    task_id: str,
    run_id: str,
    state_root: Path,
    output_json: Path,
    output_markdown: Path,
) -> tuple[dict[str, Any], OperatorRecoveryReportArtifacts]:
    payload = build_operator_recovery_payload(
        task_id=task_id,
        run_id=run_id,
        state_root=state_root,
    )
    artifacts = persist_operator_recovery_report(
        payload=payload,
        output_json=output_json,
        output_markdown=output_markdown,
    )
    payload["evidence_pointers"] = {
        "state_root": artifacts.state_root,
        "pipeline_state_json": artifacts.pipeline_state_json,
        "heartbeat_status_json": artifacts.heartbeat_status_json,
        "process_leases_json": artifacts.process_leases_json,
        "events_jsonl": artifacts.events_jsonl,
        "recovery_json": artifacts.json_report_path,
        "recovery_markdown": artifacts.markdown_report_path,
    }
    return payload, artifacts
