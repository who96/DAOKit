# Observer Relay Rollback Runbook (Non-Breaking)

## 1. Goal

Rollback observer-relay behavior changes while preserving the following invariants:

- CLI public surface remains unchanged (`init/check/run/status/replay/takeover/handoff` and existing argument names).
- Contract compatibility remains pinned to `schema_version=1.0.0` without enum expansion.
- `v1.0.0-rc1` release evidence anchors keep `docs/reports/final-run/` directory shape intact.

## 2. When To Roll Back

Start rollback if any of these signals appear:

- Relay window starts executing actions directly instead of forwarding/observing.
- Recovery loop causes takeover storms or unstable ownership churn.
- Compatibility checks detect CLI arg rename/removal or contract enum/version drift.
- Release validation reports evidence anchor breakage under `docs/reports/final-run/`.

## 3. Preconditions

1. Freeze new risky observer-relay rollouts.
2. Keep state data in place. Do not run data migrations for rollback.
3. Record current state and health before changing code.

```bash
PYTHONPATH=src python3 -m cli check --root .
PYTHONPATH=src python3 -m cli status --root . --json
PYTHONPATH=src python3 -m cli replay --root . --source events --limit 20
```

## 4. Rollback Procedure

### Step A: Create a rollback branch and revert scoped commits

Use the smallest revert scope that disables observer-relay behavior changes.

```bash
git checkout -b rollback/observer-relay-<timestamp>
# Replace SHAs with observer-relay change commits (for example DKT-019..DKT-022)
git revert --no-commit <sha1> <sha2> <sha3> <sha4>
git commit -m "rollback(observer-relay): restore pre-relay behavior without contract breaks"
```

If commit-level revert is not possible, manually restore behavior in the same paths, then continue with Step B.

### Step B: Re-run compatibility guardrails (mandatory)

These commands are the acceptance-linked checks for this rollback:

```bash
make lint
make test
PYTHONPATH=src python3 -m unittest discover -s tests/cli -p 'test_parser_compatibility.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests/contracts -p 'test_schema_compatibility_guardrails.py' -v
```

Test links:

- CLI parser surface guardrails: `tests/cli/test_parser_compatibility.py`
- Contract schema invariants guardrails: `tests/contracts/test_schema_compatibility_guardrails.py`

### Step C: Verify takeover/handoff continuity is still usable

```bash
tmpdir=$(mktemp -d)
PYTHONPATH=src python3 -m cli init --root "$tmpdir"
PYTHONPATH=src python3 -m cli run --root "$tmpdir" --task-id DKT-023 --run-id ROLLBACK-DRILL --goal "rollback drill" --simulate-interruption
PYTHONPATH=src python3 -m cli takeover --root "$tmpdir" --task-id DKT-023 --run-id ROLLBACK-DRILL --successor-thread-id rollback-thread
PYTHONPATH=src python3 -m cli handoff --root "$tmpdir" --create
rm -rf "$tmpdir"
```

Expected result: interruption path remains recoverable via existing `takeover`/`handoff` commands without schema or CLI surface changes.

### Step D: Verify release evidence anchors remain intact

```bash
test -d docs/reports/final-run
test -f docs/reports/final-run/RELEASE_SNAPSHOT.md
test -f docs/reports/final-run/run_evidence_index.md
```

## 5. Validation Matrix

| Validation target | Command(s) | Must pass |
|---|---|---|
| Baseline repository checks | `make lint` and `make test` | Yes |
| CLI command/arg compatibility | `python3 -m unittest discover -s tests/cli -p 'test_parser_compatibility.py' -v` | Yes |
| `schema_version=1.0.0` + enum compatibility | `python3 -m unittest discover -s tests/contracts -p 'test_schema_compatibility_guardrails.py' -v` | Yes |
| Runtime recovery continuity | CLI drill in Step C | Yes |
| Final-run evidence anchors | file existence checks in Step D | Yes |

## 6. Rollback Exit Criteria

Rollback is complete only if all Step B, C, and D checks pass and no CLI public command or contract schema surface has changed.
