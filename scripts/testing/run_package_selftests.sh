#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_CMD="${XUUNITY_LIGHT_UNITY_MCP_PYTHON:-}"
PYTHON_CMD="${PYTHON_CMD//\\//}"
if [[ -z "$PYTHON_CMD" ]]; then
  if command -v python3 >/dev/null 2>&1; then PYTHON_CMD="python3"; else PYTHON_CMD="python"; fi
fi

exec "$PYTHON_CMD" "$SCRIPT_DIR/run_package_selftests.py" "$@"
