from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CriterionRegistryEntry:
    criterion_id: str
    criterion: str
    evidence_refs: tuple[str, ...]
    remediation_hint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "criterion": self.criterion,
            "evidence_refs": list(self.evidence_refs),
            "remediation_hint": self.remediation_hint,
        }


@dataclass(frozen=True)
class CriterionDiagnosticEntry:
    criterion_id: str
    criterion: str
    status: str
    evidence_refs: tuple[str, ...]
    remediation_hint: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "criterion": self.criterion,
            "status": self.status,
            "evidence_refs": list(self.evidence_refs),
            "remediation_hint": self.remediation_hint,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class CriteriaDiagnosticsReport:
    schema_version: str
    registry_name: str
    task_id: str
    run_id: str
    step_id: str
    decision_status: str
    proof_id: str
    criteria: tuple[CriterionDiagnosticEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "registry_name": self.registry_name,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "decision_status": self.decision_status,
            "proof_id": self.proof_id,
            "criteria": [item.to_dict() for item in self.criteria],
        }


@dataclass(frozen=True)
class DiagnosticCorrelationRef:
    task_id: str
    run_id: str
    step_id: str | None
    event_id: str | None
    event_type: str | None
    occurred_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
        }


@dataclass(frozen=True)
class HeartbeatFreshnessDiagnostic:
    status: str
    reason_code: str | None
    observed_at: str
    last_signal_at: str | None
    silence_seconds: int
    warning_after_seconds: int | None
    stale_after_seconds: int | None
    correlation: DiagnosticCorrelationRef

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "observed_at": self.observed_at,
            "last_signal_at": self.last_signal_at,
            "silence_seconds": self.silence_seconds,
            "warning_after_seconds": self.warning_after_seconds,
            "stale_after_seconds": self.stale_after_seconds,
            "correlation": self.correlation.to_dict(),
        }


@dataclass(frozen=True)
class LeaseTransitionDiagnostic:
    transition_kind: str
    from_status: str | None
    to_status: str
    reason_code: str | None
    lease_token: str | None
    lane: str | None
    thread_id: str | None
    pid: int | None
    transition_at: str
    correlation: DiagnosticCorrelationRef

    def to_dict(self) -> dict[str, Any]:
        return {
            "transition_kind": self.transition_kind,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "reason_code": self.reason_code,
            "lease_token": self.lease_token,
            "lane": self.lane,
            "thread_id": self.thread_id,
            "pid": self.pid,
            "transition_at": self.transition_at,
            "correlation": self.correlation.to_dict(),
        }


@dataclass(frozen=True)
class TakeoverDiagnostic:
    trigger_reason_code: str
    lease_reason_code: str | None
    heartbeat_status: str | None
    decision_at: str | None
    takeover_at: str
    decision_latency_seconds: int | None
    adopted_step_ids: tuple[str, ...]
    failed_step_ids: tuple[str, ...]
    correlation: DiagnosticCorrelationRef

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_reason_code": self.trigger_reason_code,
            "lease_reason_code": self.lease_reason_code,
            "heartbeat_status": self.heartbeat_status,
            "decision_at": self.decision_at,
            "takeover_at": self.takeover_at,
            "decision_latency_seconds": self.decision_latency_seconds,
            "adopted_step_ids": list(self.adopted_step_ids),
            "failed_step_ids": list(self.failed_step_ids),
            "correlation": self.correlation.to_dict(),
        }


@dataclass(frozen=True)
class OperatorTimelineEntry:
    occurred_at: str
    category: str
    event_type: str
    severity: str
    reason_code: str | None
    summary: str
    correlation: DiagnosticCorrelationRef
    payload: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "occurred_at": self.occurred_at,
            "category": self.category,
            "event_type": self.event_type,
            "severity": self.severity,
            "reason_code": self.reason_code,
            "summary": self.summary,
            "correlation": self.correlation.to_dict(),
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class OperatorTimelineView:
    schema_version: str
    task_id: str
    run_id: str
    generated_at: str
    total_entries: int
    stale_heartbeat_events: int
    lease_transition_events: int
    takeover_events: int
    entries: tuple[OperatorTimelineEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "total_entries": self.total_entries,
            "stale_heartbeat_events": self.stale_heartbeat_events,
            "lease_transition_events": self.lease_transition_events,
            "takeover_events": self.takeover_events,
            "entries": [item.to_dict() for item in self.entries],
        }


@dataclass(frozen=True)
class ReliabilityDiagnosticsReport:
    schema_version: str
    runtime_policy: str
    task_id: str
    run_id: str
    generated_at: str
    heartbeat: HeartbeatFreshnessDiagnostic
    lease_transitions: tuple[LeaseTransitionDiagnostic, ...]
    takeover: TakeoverDiagnostic | None
    timeline: OperatorTimelineView

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "runtime_policy": self.runtime_policy,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "heartbeat": self.heartbeat.to_dict(),
            "lease_transitions": [item.to_dict() for item in self.lease_transitions],
            "takeover": None if self.takeover is None else self.takeover.to_dict(),
            "timeline": self.timeline.to_dict(),
        }
