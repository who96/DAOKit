#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-.}"
TASK_ID="DKT-018-DEMO"
RUN_ID="RUN-CORE-ROTATION"
THREAD_ID="thread-rotation"
SUCCESSOR_PID="${SUCCESSOR_PID:-77777}"
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
  --goal "Core rotation continuity demo" \
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
  --successor-thread-id "$THREAD_ID" \
  --successor-pid "$SUCCESSOR_PID"

"$PYTHON_BIN" -m cli status --root "$ROOT_DIR" --task-id "$TASK_ID" --run-id "$RUN_ID" --json
"$PYTHON_BIN" -m cli handoff --root "$ROOT_DIR" --create
"$PYTHON_BIN" -m cli handoff --root "$ROOT_DIR" --apply
"$PYTHON_BIN" -m cli replay --root "$ROOT_DIR" --source events --limit 30

printf '%s\n' "Core rotation continuity demo completed for $TASK_ID/$RUN_ID"
