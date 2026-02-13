# Operator Recovery Runbook (DKT-053)

## Purpose

This runbook defines deterministic recovery steps for:

- stale heartbeat conditions
- stale lease/Takeover escalation

All steps must align with artifacts from DKT-050 (`operator-recovery.json` and
`operator-recovery.md`) and continuity checks from DKT-052.

## Evidence Set Required

Before and during recovery, keep the following files in the incident root:

- `state/pipeline_state.json`
- `state/heartbeat_status.json`
- `state/process_leases.json`
- `state/events.jsonl`
- `reports/operator-recovery.json`
- `reports/operator-recovery.md`

Runbook commands:

```bash
RUN_ROOT=<run_root>
TASK_ID=<task_id>
RUN_ID=<run_id>

PYTHONPATH=src python3 -m cli status \
  --root "$RUN_ROOT" \
  --task-id "$TASK_ID" \
  --run-id "$RUN_ID" \
  --json \
  > "$RUN_ROOT/reports/recovery-incidents/$RUN_ID/status-before.json"

PYTHONPATH=src python3 -m cli replay \
  --root "$RUN_ROOT" \
  --source events \
  --json \
  --limit 100 \
  > "$RUN_ROOT/reports/recovery-incidents/$RUN_ID/replay-before.json"
```

## Case A: Stale Heartbeat Triage (No Immediate Takeover)

1. Confirm `state/heartbeat_status.json` shows `status == STALE`.
2. Confirm stale event exists in `state/events.jsonl` and event count is non-zero.
3. Read `reports/operator-recovery.md`:
   - section `## Stale Detection` has `Status` and `Silence Seconds`
   - section `## Continuity Outcome` is `PASS` or `REQUIRES_REVIEW` with reason
4. If workflow still has healthy lease ownership, continue monitoring.
5. If lease is missing or invalid, transition to Case B.

Case A evidence checklist:

- `reports/operator-recovery.md`
- `reports/operator-recovery.json`
- `state/heartbeat_status.json`
- `state/events.jsonl`

## Case B: Lease Takeover / Invalid Lease Escalation

1. Execute takeover:

```bash
PYTHONPATH=src python3 -m cli takeover \
  --root "$RUN_ROOT" \
  --task-id "$TASK_ID" \
  --run-id "$RUN_ID" \
  --successor-thread-id "<successor-thread-id>"
```

2. Recheck state and replay:

```bash
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
  --limit 200 \
  > "$RUN_ROOT/reports/recovery-incidents/$RUN_ID/replay-after.json"
```

3. Validate takeover in `reports/operator-recovery.json`:
   - `takeover.handoff_applied == true`
   - `takeover.takeover_at` exists
   - `continuity_assertion_results` is present and expected entries are true
4. Validate successor lease exists in `state/process_leases.json` for the successor thread.
5. Continue normal operations only when statuses are consistent.

Case B evidence checklist:

- Takeover CLI output
- `reports/operator-recovery.json`
- `reports/operator-recovery.md`
- `state/process_leases.json`
- `state/events.jsonl`
- `reports/recovery-incidents/$RUN_ID/status-after.json`
- `reports/recovery-incidents/$RUN_ID/replay-after.json`

## Incident Exit Checklist

Close incident only if all are true:

- Task/run IDs match across status, replay, and operator recovery report.
- Continuity outcome is `PASS` (or explicitly `REQUIRES_REVIEW` with risk sign-off note).
- Evidence paths are preserved under incident folder for audit traceability.
- No conflicting signals in the latest heartbeat and lease state.

## Related Drill Templates

Execute the templates in `docs/workflows/operator-recovery-drill-templates.en.md` and
verify evidence pointers before marking runbook readiness.
