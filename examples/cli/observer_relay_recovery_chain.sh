#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-.}"
TASK_ID="DKT-027-DEMO"
RUN_ID="RUN-OBSERVER-RELAY"
THREAD_ID="thread-observer-relay"
SUCCESSOR_PID="${SUCCESSOR_PID:-88888}"
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
  --goal "Observer-relay recovery chain demo" \
  --simulate-interruption
RUN_EXIT="$?"
set -e

if [[ "$RUN_EXIT" -ne 130 ]]; then
  echo "Expected interruption exit code 130, got $RUN_EXIT" >&2
  exit 1
fi

"$PYTHON_BIN" -m cli check --root "$ROOT_DIR" --json
"$PYTHON_BIN" -m cli takeover \
  --root "$ROOT_DIR" \
  --task-id "$TASK_ID" \
  --run-id "$RUN_ID" \
  --successor-thread-id "$THREAD_ID" \
  --successor-pid "$SUCCESSOR_PID"
"$PYTHON_BIN" -m cli handoff --root "$ROOT_DIR" --create
"$PYTHON_BIN" -m cli handoff --root "$ROOT_DIR" --apply

STATUS_FILE="$(mktemp)"
"$PYTHON_BIN" -m cli status \
  --root "$ROOT_DIR" \
  --task-id "$TASK_ID" \
  --run-id "$RUN_ID" \
  --json | tee "$STATUS_FILE"

"$PYTHON_BIN" - "$STATUS_FILE" <<'PY'
import json
import sys

status_path = sys.argv[1]
with open(status_path, "r", encoding="utf-8") as fh:
    payload = json.load(fh)

takeover_at = (
    payload.get("pipeline_state", {})
    .get("succession", {})
    .get("last_takeover_at")
)
if not takeover_at:
    raise SystemExit("Missing succession.last_takeover_at after takeover")

handoff_next_action = (payload.get("handoff_package") or {}).get("next_action")
if handoff_next_action != "resume":
    raise SystemExit("Expected handoff package next_action to be 'resume'")
PY

rm -f "$STATUS_FILE"
"$PYTHON_BIN" -m cli replay --root "$ROOT_DIR" --source events --limit 40

printf '%s\n' "Observer-relay recovery chain demo completed for $TASK_ID/$RUN_ID"
