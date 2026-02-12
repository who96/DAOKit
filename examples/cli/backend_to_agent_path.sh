#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-.}"

bash "$(dirname "$0")/quickstart.sh" "$ROOT_DIR"
bash "$(dirname "$0")/observer_relay_recovery_chain.sh" "$ROOT_DIR"
bash "$(dirname "$0")/recovery.sh" "$ROOT_DIR"
bash "$(dirname "$0")/core_rotation_continuity.sh" "$ROOT_DIR"

echo "Backend-to-agent transition path completed."
