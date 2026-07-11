#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONUTF8="${PYTHONUTF8:-1}"

if [[ -n "${PYTHON:-}" ]]; then
  if [[ "$PYTHON" == "py -3" ]] && command -v py >/dev/null 2>&1; then
    python_cmd=(py -3)
  else
    python_cmd=("${PYTHON//\\//}")
  fi
elif command -v python3 >/dev/null 2>&1; then
  python_cmd=(python3)
elif command -v python >/dev/null 2>&1; then
  python_cmd=(python)
elif command -v py >/dev/null 2>&1; then
  python_cmd=(py -3)
else
  echo "Python 3 was not found. Install Python 3 or set PYTHON to its executable path." >&2
  exit 1
fi

XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME="$(basename "$0")" \
  exec "${python_cmd[@]}" "$SCRIPT_DIR/run_installed_or_refresh_xuunity_mcp.py" "$@"
