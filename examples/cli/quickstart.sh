#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-.}"
TASK_ID="DKT-018-DEMO"
RUN_ID="RUN-CLI-E2E"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

"$PYTHON_BIN" -m cli init --root "$ROOT_DIR"
"$PYTHON_BIN" -m cli run \
  --root "$ROOT_DIR" \
  --task-id "$TASK_ID" \
  --run-id "$RUN_ID" \
  --goal "Exercise CLI only workflow"
"$PYTHON_BIN" -m cli status --root "$ROOT_DIR" --task-id "$TASK_ID" --run-id "$RUN_ID" --json
"$PYTHON_BIN" -m cli replay --root "$ROOT_DIR" --source events --limit 10
"$PYTHON_BIN" -m cli handoff --root "$ROOT_DIR" --create
"$PYTHON_BIN" -m cli check --root "$ROOT_DIR"
