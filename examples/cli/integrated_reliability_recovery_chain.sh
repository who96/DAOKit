#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-.}"
OUTPUT_JSON="${2:-${ROOT_DIR%/}/integrated-reliability-summary.json}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

"$PYTHON_BIN" -m reliability.scenarios.integrated_reliability \
  --scenario-root "$ROOT_DIR" \
  --output-json "$OUTPUT_JSON"

printf '%s\n' "Integrated reliability recovery scenario completed: ${OUTPUT_JSON}"
