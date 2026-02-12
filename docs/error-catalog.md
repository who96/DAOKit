# DAOKit CLI Error Catalog

This catalog maps CLI error codes to root causes and recovery actions.

## Initialization

- `E_INIT_FAILED`
  - Meaning: repository initialization hit path conflict or invalid target.
  - Typical cause: expected directory exists as file.
  - Action: fix conflicting path, rerun `python -m cli init --root <path>`.

## Health Checks

- `E_CHECK_LAYOUT_MISSING`
  - Meaning: required state files are missing.
  - Typical cause: `init` not run in selected root.
  - Action: run `python -m cli init --root <path>` and retry `check`.

- `E_CHECK_STATE_INVALID`
  - Meaning: state JSON file is malformed.
  - Typical cause: interrupted manual edits or file truncation.
  - Action: restore file from VCS or valid backup, then rerun `check`.

- `E_CHECK_HEARTBEAT_INVALID`
  - Meaning: heartbeat thresholds or timestamp payload is invalid.
  - Typical cause: non-ISO heartbeat timestamp or wrong numeric thresholds.
  - Action: repair heartbeat JSON fields and rerun.

## Workflow Execution

- `E_RUN_FAILED`
  - Meaning: run command could not complete workflow execution.
  - Typical cause: lease registration failed or runtime exception.
  - Action: inspect stderr, run `status`, then rerun with corrected inputs.

- `E_RUN_INTERRUPTED`
  - Meaning: simulated interruption path intentionally exited with code `130`.
  - Typical cause: `--simulate-interruption` option used.
  - Action: execute `takeover` to adopt active leases.

## Recovery and Continuity

- `E_STATUS_FAILED`
  - Meaning: status command could not read ledger or lease records.
  - Typical cause: invalid state file JSON.
  - Action: repair state file, rerun status.

- `E_REPLAY_FAILED`
  - Meaning: events/snapshots replay input is missing or malformed.
  - Typical cause: invalid JSON line in `events.jsonl`.
  - Action: repair log line or replay from snapshots.

- `E_TAKEOVER_FAILED`
  - Meaning: lease adoption request failed.
  - Typical cause: missing `task_id`/`run_id`, invalid successor pid, or corrupted lease registry.
  - Action: provide explicit `--task-id` + `--run-id`, inspect `state/process_leases.json`.

- `E_HANDOFF_FAILED`
  - Meaning: handoff package creation/apply failed.
  - Typical cause: ledger lacks required fields (`task_id`, `run_id`) or package mismatch.
  - Action: ensure active run state, then rerun `handoff --create` or fix package path.

- `E_INTERRUPTED`
  - Meaning: process interrupted by user signal.
  - Action: inspect with `status`, then continue via `run`, `takeover`, or `handoff --apply`.
