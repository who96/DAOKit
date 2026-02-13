from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from contracts.diagnostics_contracts import (
    DiagnosticCorrelationRef,
    HeartbeatFreshnessDiagnostic,
    LeaseTransitionDiagnostic,
    OperatorTimelineEntry,
    OperatorTimelineView,
    ReliabilityDiagnosticsReport,
    TakeoverDiagnostic,
)
from state.backend import StateBackend

SCHEMA_VERSION = "1.0.0"
RUNTIME_POLICY_LANGGRAPH_ONLY = "LANGGRAPH_ONLY"


@dataclass(frozen=True)
class ObservabilityValidationIssue:
    code: str
    severity: str
    message: str
    task_id: str
    run_id: str
    step_id: str | None
    event_id: str | None
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "event_id": self.event_id,
            "occurred_at": self.occurred_at,
        }


@dataclass(frozen=True)
class ReliabilityDiagnosticsEmission:
    report: ReliabilityDiagnosticsReport
    validation_issues: tuple[ObservabilityValidationIssue, ...]
    event_count: int
    lease_count: int

    def to_dict(self) -> dict[str, Any]:
        issues = [issue.to_dict() for issue in self.validation_issues]
        return {
            "schema_version": self.report.schema_version,
            "runtime_policy": self.report.runtime_policy,
            "task_id": self.report.task_id,
            "run_id": self.report.run_id,
            "generated_at": self.report.generated_at,
            "report": self.report.to_dict(),
            "validation": {
                "status": "PASS" if not issues else "FAIL",
                "issue_count": len(issues),
                "issues": issues,
            },
            "evidence": {
                "event_count": self.event_count,
                "lease_count": self.lease_count,
            },
        }


def build_reliability_diagnostics_report(
    *,
    task_id: str,
    run_id: str,
    heartbeat_status: Mapping[str, Any] | None,
    leases: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    generated_at: datetime | None = None,
) -> ReliabilityDiagnosticsReport:
    generated = _normalize_datetime(generated_at or datetime.now(timezone.utc))
    normalized_events = _filter_events(events=events, task_id=task_id, run_id=run_id)
    heartbeat = _build_heartbeat_freshness_diagnostic(
        task_id=task_id,
        run_id=run_id,
        heartbeat_status=heartbeat_status,
        events=normalized_events,
        generated_at=generated,
    )
    lease_transitions = _build_lease_transition_diagnostics(
        task_id=task_id,
        run_id=run_id,
        leases=leases,
        events=normalized_events,
        generated_at=generated,
    )
    takeover = _build_takeover_diagnostic(
        task_id=task_id,
        run_id=run_id,
        events=normalized_events,
        generated_at=generated,
    )
    timeline = build_operator_timeline_view(
        task_id=task_id,
        run_id=run_id,
        events=normalized_events,
        generated_at=generated,
    )

    return ReliabilityDiagnosticsReport(
        schema_version=SCHEMA_VERSION,
        runtime_policy=RUNTIME_POLICY_LANGGRAPH_ONLY,
        task_id=task_id,
        run_id=run_id,
        generated_at=generated.isoformat(),
        heartbeat=heartbeat,
        lease_transitions=lease_transitions,
        takeover=takeover,
        timeline=timeline,
    )


def emit_reliability_diagnostics(
    *,
    task_id: str,
    run_id: str,
    heartbeat_status: Mapping[str, Any] | None,
    leases: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    generated_at: datetime | None = None,
) -> ReliabilityDiagnosticsEmission:
    report = build_reliability_diagnostics_report(
        task_id=task_id,
        run_id=run_id,
        heartbeat_status=heartbeat_status,
        leases=leases,
        events=events,
        generated_at=generated_at,
    )
    filtered_events = _filter_events(events=events, task_id=task_id, run_id=run_id)
    filtered_leases = _filter_leases(leases=leases, task_id=task_id, run_id=run_id)
    issues = _validate_observability_signals(
        task_id=task_id,
        run_id=run_id,
        report=report,
        events=filtered_events,
    )
    return ReliabilityDiagnosticsEmission(
        report=report,
        validation_issues=issues,
        event_count=len(filtered_events),
        lease_count=len(filtered_leases),
    )


def emit_reliability_diagnostics_from_state_store(
    *,
    task_id: str,
    run_id: str,
    state_store: StateBackend,
    generated_at: datetime | None = None,
) -> ReliabilityDiagnosticsEmission:
    heartbeat_status = state_store.load_heartbeat_status()
    leases = _load_process_leases(state_store=state_store)
    events = _load_events(state_store=state_store)
    return emit_reliability_diagnostics(
        task_id=task_id,
        run_id=run_id,
        heartbeat_status=heartbeat_status,
        leases=leases,
        events=events,
        generated_at=generated_at,
    )


def build_operator_timeline_view(
    *,
    task_id: str,
    run_id: str,
    events: Sequence[Mapping[str, Any]],
    generated_at: datetime,
) -> OperatorTimelineView:
    entries: list[OperatorTimelineEntry] = []
    for event in events:
        entry = _timeline_entry_from_event(
            task_id=task_id,
            run_id=run_id,
            event=event,
            generated_at=generated_at,
        )
        if entry is not None:
            entries.append(entry)

    entries.sort(
        key=lambda entry: (
            entry.occurred_at,
            entry.correlation.event_id or "",
            entry.event_type,
            entry.correlation.step_id or "",
        )
    )

    return OperatorTimelineView(
        schema_version=SCHEMA_VERSION,
        task_id=task_id,
        run_id=run_id,
        generated_at=generated_at.isoformat(),
        total_entries=len(entries),
        stale_heartbeat_events=sum(1 for item in entries if item.event_type == "HEARTBEAT_STALE"),
        lease_transition_events=sum(1 for item in entries if item.category == "LEASE"),
        takeover_events=sum(1 for item in entries if item.event_type == "LEASE_TAKEOVER"),
        entries=tuple(entries),
    )


def _build_heartbeat_freshness_diagnostic(
    *,
    task_id: str,
    run_id: str,
    heartbeat_status: Mapping[str, Any] | None,
    events: Sequence[Mapping[str, Any]],
    generated_at: datetime,
) -> HeartbeatFreshnessDiagnostic:
    payload = dict(heartbeat_status or {})
    status = (_text(payload.get("status")) or "UNKNOWN").upper()
    reason_code = _text(payload.get("reason_code"))
    last_signal = _parse_optional_datetime(payload.get("last_heartbeat_at"))
    warning_after = _int_or_none(payload.get("warning_after_seconds"))
    stale_after = _int_or_none(payload.get("stale_after_seconds"))

    if last_signal is None:
        silence_seconds = stale_after or 0
    else:
        silence_seconds = max(int((generated_at - last_signal).total_seconds()), 0)

    heartbeat_event = _last_matching_event(
        events,
        lambda item: _text(item.get("event_type")) in {"HEARTBEAT_STALE", "HEARTBEAT_WARNING"},
    )
    correlation = _correlation_from_event(
        task_id=task_id,
        run_id=run_id,
        event=heartbeat_event,
        fallback_step_id=_text(payload.get("step_id")),
        fallback_occurred_at=generated_at.isoformat(),
    )

    return HeartbeatFreshnessDiagnostic(
        status=status,
        reason_code=reason_code,
        observed_at=generated_at.isoformat(),
        last_signal_at=None if last_signal is None else last_signal.isoformat(),
        silence_seconds=silence_seconds,
        warning_after_seconds=warning_after,
        stale_after_seconds=stale_after,
        correlation=correlation,
    )


def _build_lease_transition_diagnostics(
    *,
    task_id: str,
    run_id: str,
    leases: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    generated_at: datetime,
) -> tuple[LeaseTransitionDiagnostic, ...]:
    transitions: list[LeaseTransitionDiagnostic] = []

    for lease in leases:
        if _text(lease.get("task_id")) != task_id or _text(lease.get("run_id")) != run_id:
            continue

        to_status = (_text(lease.get("status")) or "UNKNOWN").upper()
        transitioned_at = _timestamp_or_default(
            first=lease.get("updated_at"),
            second=lease.get("created_at"),
            default=generated_at,
        )
        step_id = _text(lease.get("step_id"))

        transitions.append(
            LeaseTransitionDiagnostic(
                transition_kind="SNAPSHOT",
                from_status=None,
                to_status=to_status,
                reason_code=f"LEASE_{to_status}_SNAPSHOT",
                lease_token=_text(lease.get("lease_token")),
                lane=_text(lease.get("lane")),
                thread_id=_text(lease.get("thread_id")),
                pid=_int_or_none(lease.get("pid")),
                transition_at=transitioned_at,
                correlation=DiagnosticCorrelationRef(
                    task_id=task_id,
                    run_id=run_id,
                    step_id=step_id,
                    event_id=None,
                    event_type="LEASE_SNAPSHOT",
                    occurred_at=transitioned_at,
                ),
            )
        )

    for event in events:
        transition = _lease_transition_from_event(
            task_id=task_id,
            run_id=run_id,
            event=event,
            generated_at=generated_at,
        )
        if transition is not None:
            transitions.append(transition)

    transitions.sort(
        key=lambda item: (
            item.transition_at,
            item.correlation.event_id or "",
            item.correlation.step_id or "",
            item.reason_code or "",
        )
    )
    return tuple(transitions)


def _lease_transition_from_event(
    *,
    task_id: str,
    run_id: str,
    event: Mapping[str, Any],
    generated_at: datetime,
) -> LeaseTransitionDiagnostic | None:
    event_type = _text(event.get("event_type")) or "UNKNOWN"
    payload = _payload(event)
    operation = _text(payload.get("operation"))
    reason_code = _text(payload.get("reason_code"))

    transition_kind = "EVENT"
    from_status: str | None
    to_status: str
    if event_type == "LEASE_TAKEOVER":
        from_status = "ACTIVE"
        to_status = "ACTIVE"
        reason = reason_code or "LEASE_TAKEOVER"
    elif operation == "LEASE_ADOPTED":
        from_status = "ACTIVE"
        to_status = "ACTIVE"
        reason = reason_code or "VALID_UNEXPIRED_LEASE"
    elif event_type == "STEP_FAILED" and reason_code == "LEASE_NOT_ADOPTED":
        from_status = "ACTIVE"
        to_status = "FAILED"
        reason = reason_code
    else:
        return None

    transitioned_at = _timestamp_or_default(
        first=payload.get("takeover_at"),
        second=event.get("timestamp"),
        default=generated_at,
    )
    correlation = _correlation_from_event(
        task_id=task_id,
        run_id=run_id,
        event=event,
        fallback_step_id=_text(event.get("step_id")),
        fallback_occurred_at=transitioned_at,
    )

    return LeaseTransitionDiagnostic(
        transition_kind=transition_kind,
        from_status=from_status,
        to_status=to_status,
        reason_code=reason,
        lease_token=_text(payload.get("lease_token")),
        lane=_text(payload.get("lane")),
        thread_id=_text(payload.get("thread_id")),
        pid=_int_or_none(payload.get("pid")),
        transition_at=transitioned_at,
        correlation=correlation,
    )


def _build_takeover_diagnostic(
    *,
    task_id: str,
    run_id: str,
    events: Sequence[Mapping[str, Any]],
    generated_at: datetime,
) -> TakeoverDiagnostic | None:
    takeover_event = _last_matching_event(
        events,
        lambda item: _text(item.get("event_type")) == "LEASE_TAKEOVER",
    )
    if takeover_event is None:
        return None

    takeover_payload = _payload(takeover_event)
    takeover_at = _timestamp_or_default(
        first=takeover_payload.get("takeover_at"),
        second=takeover_event.get("timestamp"),
        default=generated_at,
    )
    decision_event = _last_decision_event_before(events=events, takeover_at=takeover_at)
    decision_payload = _payload(decision_event) if decision_event is not None else {}
    decision_at = _timestamp_or_none(
        first=decision_payload.get("decided_at"),
        second=decision_event.get("timestamp") if decision_event is not None else None,
    )
    latency_seconds = _decision_latency_seconds(decision_at=decision_at, takeover_at=takeover_at)

    correlation = _correlation_from_event(
        task_id=task_id,
        run_id=run_id,
        event=takeover_event,
        fallback_step_id=_text(takeover_event.get("step_id")),
        fallback_occurred_at=takeover_at,
    )

    return TakeoverDiagnostic(
        trigger_reason_code=_text(takeover_payload.get("reason_code")) or "MANUAL_TAKEOVER",
        lease_reason_code=_text(decision_payload.get("lease_reason_code")),
        heartbeat_status=_text(decision_payload.get("heartbeat_status")),
        decision_at=decision_at,
        takeover_at=takeover_at,
        decision_latency_seconds=latency_seconds,
        adopted_step_ids=_text_tuple(takeover_payload.get("adopted_step_ids")),
        failed_step_ids=_text_tuple(takeover_payload.get("failed_step_ids")),
        correlation=correlation,
    )


def _timeline_entry_from_event(
    *,
    task_id: str,
    run_id: str,
    event: Mapping[str, Any],
    generated_at: datetime,
) -> OperatorTimelineEntry | None:
    event_type = _text(event.get("event_type")) or "UNKNOWN"
    payload = _payload(event)
    operation = _text(payload.get("operation"))
    reason_code = _text(payload.get("reason_code")) or _text(payload.get("decision_reason_code"))

    category: str | None
    if event_type.startswith("HEARTBEAT_"):
        category = "HEARTBEAT"
    elif event_type == "LEASE_TAKEOVER" or operation in {"HANDOFF_APPLIED", "HANDOFF_APPLY_FAILED"}:
        category = "TAKEOVER"
    elif operation == "LEASE_ADOPTED" or reason_code == "LEASE_NOT_ADOPTED":
        category = "LEASE"
    else:
        return None

    occurred_at = _timestamp_or_default(
        first=payload.get("takeover_at"),
        second=event.get("timestamp"),
        default=generated_at,
    )
    correlation = _correlation_from_event(
        task_id=task_id,
        run_id=run_id,
        event=event,
        fallback_step_id=_text(event.get("step_id")),
        fallback_occurred_at=occurred_at,
    )
    return OperatorTimelineEntry(
        occurred_at=occurred_at,
        category=category,
        event_type=event_type,
        severity=(_text(event.get("severity")) or "INFO").upper(),
        reason_code=reason_code,
        summary=_event_summary(event_type=event_type, operation=operation, step_id=correlation.step_id),
        correlation=correlation,
        payload=dict(payload),
    )


def _last_decision_event_before(
    *,
    events: Sequence[Mapping[str, Any]],
    takeover_at: str,
) -> Mapping[str, Any] | None:
    takeover_dt = _parse_optional_datetime(takeover_at)
    if takeover_dt is None:
        return None

    matched: list[Mapping[str, Any]] = []
    for event in events:
        payload = _payload(event)
        if payload.get("stage") != "decide" or payload.get("takeover_required") is not True:
            continue
        event_dt = _parse_optional_datetime(payload.get("decided_at")) or _parse_optional_datetime(
            event.get("timestamp")
        )
        if event_dt is None or event_dt > takeover_dt:
            continue
        matched.append(event)

    if not matched:
        return None
    return sorted(
        matched,
        key=lambda item: (
            _timestamp_or_default(first=_payload(item).get("decided_at"), second=item.get("timestamp"), default=takeover_dt),
            _text(item.get("event_id")) or "",
        ),
    )[-1]


def _event_summary(*, event_type: str, operation: str | None, step_id: str | None) -> str:
    if event_type == "HEARTBEAT_STALE":
        return "Heartbeat became stale"
    if event_type == "HEARTBEAT_WARNING":
        return "Heartbeat entered warning"
    if event_type == "LEASE_TAKEOVER":
        return "Lease takeover executed"
    if operation == "LEASE_ADOPTED":
        return f"Lease adopted for step {step_id or 'unknown'}"
    if operation == "HANDOFF_APPLIED":
        return "Handoff package applied after takeover"
    if operation == "HANDOFF_APPLY_FAILED":
        return "Handoff package apply failed"
    if event_type == "STEP_FAILED":
        return f"Step {step_id or 'unknown'} failed because lease was not adopted"
    return event_type


def _decision_latency_seconds(*, decision_at: str | None, takeover_at: str) -> int | None:
    decision_dt = _parse_optional_datetime(decision_at)
    takeover_dt = _parse_optional_datetime(takeover_at)
    if decision_dt is None or takeover_dt is None:
        return None
    latency = int((takeover_dt - decision_dt).total_seconds())
    if latency < 0:
        return None
    return latency


def _correlation_from_event(
    *,
    task_id: str,
    run_id: str,
    event: Mapping[str, Any] | None,
    fallback_step_id: str | None,
    fallback_occurred_at: str,
) -> DiagnosticCorrelationRef:
    if event is None:
        return DiagnosticCorrelationRef(
            task_id=task_id,
            run_id=run_id,
            step_id=fallback_step_id,
            event_id=None,
            event_type=None,
            occurred_at=fallback_occurred_at,
        )

    occurred = _timestamp_or_default(
        first=_payload(event).get("takeover_at"),
        second=event.get("timestamp"),
        default=_normalize_datetime(datetime.fromisoformat(fallback_occurred_at)),
    )
    return DiagnosticCorrelationRef(
        task_id=task_id,
        run_id=run_id,
        step_id=_text(event.get("step_id")) or fallback_step_id,
        event_id=_text(event.get("event_id")),
        event_type=_text(event.get("event_type")),
        occurred_at=occurred,
    )


def _filter_events(
    *,
    events: Sequence[Mapping[str, Any]],
    task_id: str,
    run_id: str,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for event in events:
        if _text(event.get("task_id")) != task_id or _text(event.get("run_id")) != run_id:
            continue
        selected.append(dict(event))
    return selected


def _filter_leases(
    *,
    leases: Sequence[Mapping[str, Any]],
    task_id: str,
    run_id: str,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for lease in leases:
        if _text(lease.get("task_id")) != task_id or _text(lease.get("run_id")) != run_id:
            continue
        selected.append(dict(lease))
    return selected


def _validate_observability_signals(
    *,
    task_id: str,
    run_id: str,
    report: ReliabilityDiagnosticsReport,
    events: Sequence[Mapping[str, Any]],
) -> tuple[ObservabilityValidationIssue, ...]:
    issues: list[ObservabilityValidationIssue] = []

    stale_events = [event for event in events if _text(event.get("event_type")) == "HEARTBEAT_STALE"]
    takeover_events = [event for event in events if _text(event.get("event_type")) == "LEASE_TAKEOVER"]
    decision_events = [
        event
        for event in events
        if _payload(event).get("stage") == "decide" and _payload(event).get("takeover_required") is True
    ]
    lease_adopted_step_ids = {
        _text(event.get("step_id"))
        for event in events
        if _text(_payload(event).get("operation")) == "LEASE_ADOPTED"
    }
    lease_adopted_step_ids.discard(None)

    lease_failed_step_ids = {
        _text(event.get("step_id"))
        for event in events
        if _text(event.get("event_type")) == "STEP_FAILED"
        and _text(_payload(event).get("reason_code")) == "LEASE_NOT_ADOPTED"
    }
    lease_failed_step_ids.discard(None)

    if report.heartbeat.status == "STALE" and not stale_events:
        issues.append(
            _make_validation_issue(
                code="MISSING_HEARTBEAT_STALE_SIGNAL",
                severity="ERROR",
                message="heartbeat status is STALE but no HEARTBEAT_STALE event exists",
                task_id=task_id,
                run_id=run_id,
                correlation=report.heartbeat.correlation,
                fallback_occurred_at=report.heartbeat.observed_at,
            )
        )

    if decision_events and report.takeover is None:
        latest_decision = _latest_event(decision_events)
        correlation = _correlation_from_event(
            task_id=task_id,
            run_id=run_id,
            event=latest_decision,
            fallback_step_id=None,
            fallback_occurred_at=report.generated_at,
        )
        issues.append(
            _make_validation_issue(
                code="MISSING_TAKEOVER_EVENT",
                severity="ERROR",
                message="takeover decision exists but LEASE_TAKEOVER event is missing",
                task_id=task_id,
                run_id=run_id,
                correlation=correlation,
                fallback_occurred_at=report.generated_at,
            )
        )

    if report.takeover is not None:
        takeover = report.takeover
        if not decision_events:
            issues.append(
                _make_validation_issue(
                    code="MISSING_TAKEOVER_DECISION_SIGNAL",
                    severity="ERROR",
                    message="LEASE_TAKEOVER event exists but decision signal is missing",
                    task_id=task_id,
                    run_id=run_id,
                    correlation=takeover.correlation,
                    fallback_occurred_at=takeover.takeover_at,
                )
            )

        if takeover.decision_latency_seconds is None:
            issues.append(
                _make_validation_issue(
                    code="INCONSISTENT_TAKEOVER_TIMING",
                    severity="ERROR",
                    message="takeover timing is inconsistent or incomplete",
                    task_id=task_id,
                    run_id=run_id,
                    correlation=takeover.correlation,
                    fallback_occurred_at=takeover.takeover_at,
                )
            )

        if takeover.correlation.event_id is None or takeover.correlation.occurred_at is None:
            issues.append(
                _make_validation_issue(
                    code="MISSING_TAKEOVER_CORRELATION",
                    severity="ERROR",
                    message="takeover correlation is missing event_id or occurred_at",
                    task_id=task_id,
                    run_id=run_id,
                    correlation=takeover.correlation,
                    fallback_occurred_at=takeover.takeover_at,
                )
            )

        missing_adopted = sorted(set(takeover.adopted_step_ids) - lease_adopted_step_ids)
        if missing_adopted:
            issues.append(
                _make_validation_issue(
                    code="MISSING_LEASE_ADOPTED_SIGNAL",
                    severity="ERROR",
                    message=(
                        "takeover adopted steps missing LEASE_ADOPTED signals: "
                        + ",".join(missing_adopted)
                    ),
                    task_id=task_id,
                    run_id=run_id,
                    correlation=takeover.correlation,
                    fallback_occurred_at=takeover.takeover_at,
                )
            )

        missing_failed = sorted(set(takeover.failed_step_ids) - lease_failed_step_ids)
        if missing_failed:
            issues.append(
                _make_validation_issue(
                    code="MISSING_LEASE_FAILURE_SIGNAL",
                    severity="ERROR",
                    message=(
                        "takeover failed steps missing LEASE_NOT_ADOPTED failure signals: "
                        + ",".join(missing_failed)
                    ),
                    task_id=task_id,
                    run_id=run_id,
                    correlation=takeover.correlation,
                    fallback_occurred_at=takeover.takeover_at,
                )
            )

    for transition in report.lease_transitions:
        if transition.transition_kind != "EVENT":
            continue
        correlation = transition.correlation
        if correlation.event_id is not None and correlation.occurred_at is not None:
            continue
        issues.append(
            _make_validation_issue(
                code="MISSING_LEASE_TRANSITION_CORRELATION",
                severity="WARN",
                message="lease transition event is missing correlation event_id or occurred_at",
                task_id=task_id,
                run_id=run_id,
                correlation=correlation,
                fallback_occurred_at=transition.transition_at,
            )
        )

    sorted_issues = sorted(
        issues,
        key=lambda issue: (
            issue.code,
            issue.occurred_at,
            issue.event_id or "",
            issue.step_id or "",
        ),
    )
    return tuple(sorted_issues)


def _make_validation_issue(
    *,
    code: str,
    severity: str,
    message: str,
    task_id: str,
    run_id: str,
    correlation: DiagnosticCorrelationRef,
    fallback_occurred_at: str,
) -> ObservabilityValidationIssue:
    occurred_at = correlation.occurred_at or fallback_occurred_at
    return ObservabilityValidationIssue(
        code=code,
        severity=severity,
        message=message,
        task_id=task_id,
        run_id=run_id,
        step_id=correlation.step_id,
        event_id=correlation.event_id,
        occurred_at=occurred_at,
    )


def _latest_event(events: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if not events:
        return None
    return sorted(
        events,
        key=lambda item: (
            _timestamp_or_default(
                first=_payload(item).get("takeover_at"),
                second=item.get("timestamp"),
                default=datetime.fromtimestamp(0, tz=timezone.utc),
            ),
            _text(item.get("event_id")) or "",
        ),
    )[-1]


def _load_process_leases(*, state_store: StateBackend) -> list[dict[str, Any]]:
    try:
        payload = state_store.load_leases()
    except Exception:
        return []
    leases = payload.get("leases")
    if not isinstance(leases, Sequence) or isinstance(leases, (str, bytes, bytearray)):
        return []
    return [dict(lease) for lease in leases if isinstance(lease, Mapping)]


def _load_events(*, state_store: StateBackend) -> list[dict[str, Any]]:
    events_path = Path(state_store.events_path)
    if not events_path.exists() or not events_path.is_file():
        return []

    events: list[dict[str, Any]] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        payload = line.strip()
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, Mapping):
            events.append(dict(parsed))
    return events


def _last_matching_event(
    events: Sequence[Mapping[str, Any]],
    predicate: Any,
) -> Mapping[str, Any] | None:
    matched = [event for event in events if predicate(event)]
    if not matched:
        return None
    return sorted(
        matched,
        key=lambda item: (
            _timestamp_or_default(
                first=_payload(item).get("takeover_at"),
                second=item.get("timestamp"),
                default=datetime.fromtimestamp(0, tz=timezone.utc),
            ),
            _text(item.get("event_id")) or "",
        ),
    )[-1]


def _payload(event: Mapping[str, Any] | None) -> dict[str, Any]:
    if event is None:
        return {}
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return {}
    return dict(payload)


def _timestamp_or_none(*, first: object, second: object) -> str | None:
    first_dt = _parse_optional_datetime(first)
    if first_dt is not None:
        return first_dt.isoformat()
    second_dt = _parse_optional_datetime(second)
    if second_dt is not None:
        return second_dt.isoformat()
    return None


def _timestamp_or_default(*, first: object, second: object, default: datetime) -> str:
    preferred = _timestamp_or_none(first=first, second=second)
    if preferred is not None:
        return preferred
    return _normalize_datetime(default).isoformat()


def _parse_optional_datetime(value: object) -> datetime | None:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _normalize_datetime(parsed)


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    items: list[str] = []
    for raw in value:
        text = _text(raw)
        if text is None:
            continue
        items.append(text)
    return tuple(items)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
