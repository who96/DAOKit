#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-.}"
TASK_ID="DKT-018-DEMO"
RUN_ID="RUN-CLI-INT"
THREAD_ID="thread-recover"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

"$PYTHON_BIN" -m cli init --root "$ROOT_DIR"

set +e
"$PYTHON_BIN" -m cli run \
  --root "$ROOT_DIR" \
  --task-id "$TASK_ID" \
  --run-id "$RUN_ID" \
  --goal "Interruption recovery" \
  --simulate-interruption
RUN_EXIT="$?"
set -e

if [[ "$RUN_EXIT" -ne 130 ]]; then
  echo "Expected interruption exit code 130, got $RUN_EXIT" >&2
  exit 1
fi

"$PYTHON_BIN" -m cli takeover \
  --root "$ROOT_DIR" \
  --task-id "$TASK_ID" \
  --run-id "$RUN_ID" \
  --successor-thread-id "$THREAD_ID"
"$PYTHON_BIN" -m cli status --root "$ROOT_DIR" --task-id "$TASK_ID" --run-id "$RUN_ID" --json
"$PYTHON_BIN" -m cli replay --root "$ROOT_DIR" --source events --limit 20
"$PYTHON_BIN" -m cli handoff --root "$ROOT_DIR" --create
