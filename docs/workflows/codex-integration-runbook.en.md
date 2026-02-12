# Codex Integration Runbook (Backend Reproducible)

Language: **English** | [中文](codex-integration-runbook.zh-CN.md)

## 1. Purpose

This runbook lets backend engineers reproduce the integrated runtime path where LangGraph controls lifecycle,
LangChain orchestrates tools/retrieval, RAG provides advisory context, and Codex shim executes dispatch actions.

## 2. Prerequisites

1. Repository is initialized and dependencies are available.
2. Commands run from repository root.
3. `PYTHONPATH=src` is set for Python module commands.
4. You do not change CLI external argument names.

## 3. Reproducible command flow

### Step 1: Create a sandbox for this run

```bash
RUN_ROOT=.artifacts/manual_runs/codex_integration_demo
mkdir -p "$RUN_ROOT"
```

Expected: directory exists and is writable.

### Step 2: Execute integrated reliability chain script

```bash
bash examples/cli/integrated_reliability_recovery_chain.sh \
  "$RUN_ROOT/scenario" \
  "$RUN_ROOT/integrated-reliability-summary.json"
```

Expected output contains:

- `Integrated reliability recovery scenario completed:`
- A JSON path ending with `integrated-reliability-summary.json`

### Step 3: Validate runtime role checkpoints from summary JSON

```bash
python3 - <<'PY'
import json
from pathlib import Path

p = Path('.artifacts/manual_runs/codex_integration_demo/integrated-reliability-summary.json')
data = json.loads(p.read_text())
keys = [
    'runtime_mode',
    'resolved_runtime_engine',
    'runtime_class',
]
for k in keys:
    print(f"{k}={data.get(k)}")
print("takeover.handoff_applied=", data.get('takeover', {}).get('handoff_applied'))
print("checks.status_replay_consistent_after_recovery=", data.get('checks', {}).get('status_replay_consistent_after_recovery'))
print("final_state.status=", data.get('status_final', {}).get('pipeline_state', {}).get('status'))
PY
```

Expected values:

- `runtime_mode=integrated`
- `resolved_runtime_engine=langgraph`
- `runtime_class=LangGraphOrchestratorRuntime`
- `takeover.handoff_applied=True`
- `checks.status_replay_consistent_after_recovery=True`
- `final_state.status=DONE`

### Step 4: Inspect state and events for the same run

```bash
PYTHONPATH=src python3 -m cli status \
  --root "$RUN_ROOT/scenario" \
  --task-id DKT-036 \
  --run-id RUN-INTEGRATED-RELIABILITY \
  --json

PYTHONPATH=src python3 -m cli replay \
  --root "$RUN_ROOT/scenario" \
  --source events \
  --limit 20
```

Expected:

- `status` output includes contract-compatible objects (`pipeline_state`, `heartbeat_status`, `leases`).
- replay output is non-empty and consistent with summary checks.

### Step 5: Run baseline repository verification

```bash
make lint && make test
```

Expected: command exits `0`.

## 4. Reference evidence from finalized integration wave

The following tracked artifacts demonstrate the same flow already accepted in DKT-036:

- `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/report.md`
- `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/verification.log`
- `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/integrated-reliability-summary.json`
- `docs/reports/final-run/evidence/agent_runs/DKT-036_20260212T093654Z_a62b87a/reports/DKT-036/integrated-reliability-summary-from-script.json`

## 5. Command-to-role mapping

| Command / Artifact | Runtime role it validates |
| --- | --- |
| `integrated_reliability_recovery_chain.sh` | Dispatch to integrated runtime with recovery operations |
| Summary JSON checkpoints | LangGraph runtime ownership + recovery continuity |
| `cli status` and `cli replay` | Ledger/event consistency and traceability |
| `make lint && make test` | Baseline project verification gate |

## 6. Guardrails

- Keep CLI command and argument names unchanged.
- Keep `schema_version=1.0.0` semantics unchanged.
- Keep `v1.0.0-rc1` release-anchor semantics and `docs/reports/final-run/` evidence structure unchanged.
