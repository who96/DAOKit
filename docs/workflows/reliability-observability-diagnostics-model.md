# v1.2 Reliability Observability Diagnostics Model (DKT-048)

## Scope

This document defines the deterministic diagnostics model for stale heartbeat, lease lifecycle transitions, takeover reasoning/timing, and task/run/step correlation.  
The model is designed for report and dashboard consumption without manual event stitching.

## Contract Objects

The model is implemented in:

- `src/contracts/diagnostics_contracts.py`
- `src/reliability/diagnostics.py`

### 1. Correlation Reference

`DiagnosticCorrelationRef` is the common join key attached to every diagnostics object and timeline entry:

- `task_id`
- `run_id`
- `step_id` (nullable)
- `event_id` (nullable)
- `event_type` (nullable)
- `occurred_at` (nullable ISO-8601, UTC-normalized)

### 2. Heartbeat Freshness Diagnostic

`HeartbeatFreshnessDiagnostic` describes stale/warning/running freshness state:

- `status`
- `reason_code`
- `observed_at`
- `last_signal_at`
- `silence_seconds`
- `warning_after_seconds`
- `stale_after_seconds`
- `correlation`

Determinism rule:
- `silence_seconds = max(generated_at - last_heartbeat_at, 0)` when `last_heartbeat_at` exists.
- If no signal exists, fallback to `stale_after_seconds` (or `0` when absent).

### 3. Lease Transition Diagnostic

`LeaseTransitionDiagnostic` captures lease status changes from two sources:

- Snapshot source (`transition_kind=SNAPSHOT`) from current lease records.
- Event source (`transition_kind=EVENT`) from reliability events (`LEASE_TAKEOVER`, `LEASE_ADOPTED`, `LEASE_NOT_ADOPTED`).

Fields:

- `transition_kind`
- `from_status` (nullable)
- `to_status`
- `reason_code`
- `lease_token` (nullable)
- `lane` (nullable)
- `thread_id` (nullable)
- `pid` (nullable)
- `transition_at`
- `correlation`

### 4. Takeover Diagnostic

`TakeoverDiagnostic` binds takeover trigger, lease validation reason, and timing:

- `trigger_reason_code`
- `lease_reason_code` (nullable)
- `heartbeat_status` (nullable)
- `decision_at` (nullable)
- `takeover_at`
- `decision_latency_seconds` (nullable)
- `adopted_step_ids`
- `failed_step_ids`
- `correlation`

Timing rule:
- `decision_latency_seconds = takeover_at - decision_at` (seconds).
- Negative latency is rejected to `null`.

### 5. Operator Timeline View

`OperatorTimelineView` is the dashboard/report-facing sequence:

- `schema_version`
- `task_id`
- `run_id`
- `generated_at`
- `total_entries`
- `stale_heartbeat_events`
- `lease_transition_events`
- `takeover_events`
- `entries[]`

`OperatorTimelineEntry` fields:

- `occurred_at`
- `category` (`HEARTBEAT` | `LEASE` | `TAKEOVER`)
- `event_type`
- `severity`
- `reason_code` (nullable)
- `summary`
- `correlation`
- `payload`

Ordering rule:
- Timeline entries are sorted by `(occurred_at, event_id, event_type, step_id)` for deterministic replay.

### 6. Top-Level Report

`ReliabilityDiagnosticsReport` is the model package for upper layers:

- `schema_version` (`1.0.0`)
- `runtime_policy` (`LANGGRAPH_ONLY`)
- `task_id`
- `run_id`
- `generated_at`
- `heartbeat`
- `lease_transitions[]`
- `takeover` (nullable)
- `timeline`

## Correlation Rules

1. All diagnostics records MUST carry `task_id` and `run_id`.
2. `step_id` is preserved when event/lease scope is step-specific; otherwise null.
3. `event_id` and `event_type` are propagated whenever source events exist.
4. Cross-run events are excluded at extraction time (`task_id/run_id` match required).

## LangGraph-only and Compatibility Constraints

This diagnostics model is additive and does not alter runtime engine switching behavior:

- Runtime policy is explicitly pinned to `LANGGRAPH_ONLY`.
- No CLI parameter names are changed.
- No schema semantic break is introduced (`schema_version=1.0.0` remains intact).
- Existing final-run evidence topology under `docs/reports/final-run/` remains unchanged.

## Verification Targets

Model behavior is validated by:

- `tests/reliability/test_observability_diagnostics_model.py`

Coverage focus:

- Serialization stability for all diagnostics objects.
- Task/run/step correlation linkage.
- Takeover reason/timing derivation.
- Deterministic timeline ordering and filtering.
