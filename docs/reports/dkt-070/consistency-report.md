# Cross-Backend Consistency Report

- Task ID: `DKT-070`
- Run ID: `DKT-070_20260213T132036Z_7vugm3t`
- Generated At: `2026-02-13T16:27:07.201310+00:00`

## Summary

- Backends: `filesystem, sqlite`
- Scenarios: `integrated_reliability, text_input_minimal_flow, checkpoint_recovery`
- Overall: `PASS`

## Tolerance

- Notes: Equivalence compares backend outputs after canonicalization. Canonicalization keeps only contract-relevant signals and drops volatile ids/timestamps and absolute filesystem paths.
- Ignored volatile fields:
  - `event_id`
  - `checkpoint_id`
  - `lease_token`
  - `timestamp`
  - `updated_at`
  - `scenario_root`
  - `state_dir`
  - `events_log`
  - `handoff_package`
  - `runtime_settings`
  - `operator_recovery_outputs`
  - `command_log`

## Scenario Results

### integrated_reliability

- Equivalent: PASS

### text_input_minimal_flow

- Equivalent: PASS

### checkpoint_recovery

- Equivalent: PASS

