# Operator CLI Recovery Runbook

This runbook is for operators recovering DAOKit runs without GUI tooling.

## Scope

Use this when a run was interrupted and you need deterministic recovery from CLI only.

## Baseline Validation

Run before any takeover:

```bash
python -m cli check --root .
python -m cli status --root . --json
```

Confirm:

- state files are readable
- target run has active or recently active lease records
- `task_id` and `run_id` are known

## Forced Interruption Recovery

### 1) Reproduce interrupted state (or detect an existing one)

```bash
python -m cli run \
  --root . \
  --task-id DKT-016 \
  --run-id RUN-CLI-INT \
  --goal "Interruption recovery" \
  --simulate-interruption
```

Expected: exit code `130`, lease remains ACTIVE.

### 2) Adopt leases as successor

```bash
python -m cli takeover \
  --root . \
  --task-id DKT-016 \
  --run-id RUN-CLI-INT \
  --successor-thread-id thread-recover
```

Expected: JSON payload with `adopted_step_ids`.

### 3) Verify state continuity

```bash
python -m cli status --root . --task-id DKT-016 --run-id RUN-CLI-INT --json
python -m cli replay --root . --source events --limit 20
```

Expected:

- `succession.last_takeover_at` is populated
- replay shows `SUCCESSION_ACCEPTED`

### 4) Create handoff package for core rotation

```bash
python -m cli handoff --root . --create
```

Optional apply in new window/session:

```bash
python -m cli handoff --root . --apply
```

## Troubleshooting Matrix

- `check` returns `E_CHECK_LAYOUT_MISSING`
  - Cause: root not initialized.
  - Fix: run `python -m cli init --root .`.

- `takeover` returns `E_TAKEOVER_FAILED: run id is required`
  - Cause: run metadata missing in ledger.
  - Fix: pass explicit `--task-id` and `--run-id`.

- `handoff --apply` returns package mismatch
  - Cause: package belongs to different task/run.
  - Fix: choose matching package path or rerun `handoff --create` on current ledger.

- `replay` fails with invalid JSON line
  - Cause: events log corruption.
  - Fix: repair malformed JSON line and rerun.

See `docs/error-catalog.md` for full code reference.
