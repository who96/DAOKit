# Engine Rollout Rollback Runbook (Legacy <-> Integrated)

## 1. Goal

Roll runtime execution between `legacy` and `integrated` modes without changing public CLI argument names and without contract/release anchor drift.

Invariants:

- Keep CLI command/argument surface stable (`init/check/run/status/replay/takeover/handoff`).
- Keep contract semantics pinned to `schema_version=1.0.0`.
- Keep `v1.0.0-rc1` release anchor and `docs/reports/final-run/` evidence topology unchanged.

## 2. Selector Inputs (Non-Breaking)

Rollout controls are internal and optional:

1. Environment selectors

```bash
DAOKIT_RUNTIME_ENGINE=legacy|langgraph
DAOKIT_ENGINE_MODE=legacy|integrated
```

2. Optional runtime settings file (no CLI arg required):

`state/runtime_settings.json`

```json
{
  "runtime": {
    "mode": "integrated"
  }
}
```

Precedence used at runtime: explicit runtime selector > env > optional config file > default `legacy`.

## 3. Rollback Triggers

Start rollback to `legacy` when any of these appears:

- Integrated run fails acceptance repeatedly.
- Optional dependency degradation (`langgraph` / `langchain`) causes unstable behavior.
- Compatibility tests indicate CLI surface or contract anchor drift.

## 4. Rollback Procedure

### Step A: Freeze rollout and force legacy engine

Fast rollback via env:

```bash
export DAOKIT_RUNTIME_ENGINE=legacy
```

Or rollback via internal config:

```bash
cat > state/runtime_settings.json <<'JSON'
{
  "runtime": {
    "mode": "legacy"
  }
}
JSON
```

No new CLI flags are required.

### Step B: Sanity run with unchanged CLI interface

```bash
tmpdir=$(mktemp -d)
PYTHONPATH=src python3 -m cli init --root "$tmpdir"
PYTHONPATH=src python3 -m cli run --root "$tmpdir" --task-id DKT-035 --run-id ROLLBACK-DRILL --goal "rollback drill"
PYTHONPATH=src python3 -m cli status --root "$tmpdir" --task-id DKT-035 --run-id ROLLBACK-DRILL --json
rm -rf "$tmpdir"
```

### Step C: Run compatibility guardrails (mandatory)

```bash
python3 -m compileall src tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests/cli -p 'test_*.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests/contracts -p 'test_*.py' -v
```

### Step D: Release anchor checks

```bash
PYTHONPATH=src python3 -m unittest tests.contracts.test_release_evidence_anchors -v
```

## 5. Test Links

- CLI surface freeze: `tests/cli/test_parser_compatibility.py`
- CLI rollout controls (no new public flags): `tests/cli/test_engine_rollout_compatibility.py`
- Contract schema compatibility: `tests/contracts/test_schema_compatibility_guardrails.py`
- Rollout contract guardrails: `tests/contracts/test_engine_rollout_contract_guardrails.py`
- Release evidence anchors: `tests/contracts/test_release_evidence_anchors.py`

## 6. Evidence Expectations

Record command evidence with both marker styles in verification logs:

- `=== COMMAND ENTRY N START/END ===`
- `Command: <exact command>`

For DKT-035 S1 execution, evidence should be written to:

- `.artifacts/agent_runs/DKT-035_20260212T091621Z_46fc1c7/S1/verification.log`
- `.artifacts/agent_runs/DKT-035_20260212T091621Z_46fc1c7/S1/task-summary.md`

## 7. Exit Criteria

Rollback is complete only if all compatibility and release-anchor checks pass, and runtime can execute with `legacy` selector using unchanged CLI arguments.
