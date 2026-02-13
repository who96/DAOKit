# Operator Recovery Drill Templates (DKT-053)

## Objective

These templates produce reproducible recovery evidence for stale heartbeat and stale lease
takeover scenarios. Each drill must produce evidence files that are directly consumable by the
DKT-053 runbook and DKT-052 continuity checks.

## Preconditions

- `PYTHONPATH=src`
- `RUN_ROOT` points to a writable scenario workspace
- `TASK_ID` and `RUN_ID` are known
- DKT-050 operator report generation is available (`reports/operator-recovery.json` and `reports/operator-recovery.md`)

## Template 1: Reproducible Stale Heartbeat Drill (T-053-DRILL-01)

### Goal

Validate stale heartbeat detection, dashboard visibility, and evidence collection without
operator-triggered takeover.

### Steps

```bash
RUN_ROOT=./artifacts/drill-stale-heartbeat-$RUN_ID
TASK_ID=DKT-050
RUN_ID=stale-heartbeat-drift-01

bash examples/cli/integrated_reliability_recovery_chain.sh \
  "$RUN_ROOT" \
  "$RUN_ROOT/operator-recovery-summary.json"
```

### Required Evidence

- `state/heartbeat_status.json`
- `reports/operator-recovery.json`
- `reports/operator-recovery.md`
- `state/events.jsonl`
- `docs/workflows/operator-recovery-runbook.en.md` reference in the audit note

### Expected Result

- `heartbeat.first_tick.status == STALE`
- `operator-recovery.json.checks.status_replay_consistent_after_recovery == true`
- `reports/operator-recovery.md` contains Stale Detection section

## Template 2: Takeover Escalation Drill (T-053-DRILL-02)

### Goal

Validate manual takeover and continuity evidence capture when stale heartbeat needs ownership transfer.

### Steps

```bash
RUN_ROOT=./artifacts/drill-takeover-$RUN_ID
TASK_ID=DKT-050
RUN_ID=takeover-drill-02
SUCCESSOR=operator-recovery-02

PYTHONPATH=src python3 -m cli status \
  --root "$RUN_ROOT" \
  --task-id "$TASK_ID" \
  --run-id "$RUN_ID" \
  --json \
  > "$RUN_ROOT/reports/recovery-incidents/$RUN_ID/status-before.json"

PYTHONPATH=src python3 -m cli takeover \
  --root "$RUN_ROOT" \
  --task-id "$TASK_ID" \
  --run-id "$RUN_ID" \
  --successor-thread-id "$SUCCESSOR" \
  > "$RUN_ROOT/reports/recovery-incidents/$RUN_ID/takeover.log"

PYTHONPATH=src python3 -m cli status \
  --root "$RUN_ROOT" \
  --task-id "$TASK_ID" \
  --run-id "$RUN_ID" \
  --json \
  > "$RUN_ROOT/reports/recovery-incidents/$RUN_ID/status-after.json"

PYTHONPATH=src python3 -m cli replay \
  --root "$RUN_ROOT" \
  --source events \
  --json \
  --limit 120 \
  > "$RUN_ROOT/reports/recovery-incidents/$RUN_ID/replay-after.json"
```

### Required Evidence

- `state/process_leases.json`
- `reports/operator-recovery.json`
- `state/events.jsonl`
- `$RUN_ROOT/reports/recovery-incidents/$RUN_ID/takeover.log`
- `$RUN_ROOT/reports/recovery-incidents/$RUN_ID/status-after.json`
- `$RUN_ROOT/reports/recovery-incidents/$RUN_ID/replay-after.json`

### Expected Result

- `operator-recovery.json.takeover.handoff_applied == true`
- `operator-recovery.json.continuity_assertion_results` has non-failing required assertions
- latest `state/events.jsonl` has takeover events after command completion

## Template 3: Continuous Drill Readiness Checklist (T-053-DRILL-03)

### Goal

Validate that evidence package is complete for readiness review.

### Checklist

1. Preserve run artifacts in one folder under `reports/recovery-incidents/<run_id>/`.
2. Include command logs with timestamps and outputs.
3. Confirm operator dashboard values map to state and event timeline:
   - `run_id`/`task_id` in status/replay/reports are consistent
   - continuity outcome is either `PASS` or justified `REQUIRES_REVIEW`
4. Record outcome and blocker list in `docs/reports/dkt-053/report.md`.

### Required Artifact Bundle

- `report.md`
- `audit-summary.md`
- `verification.log`
- Drill outputs above
