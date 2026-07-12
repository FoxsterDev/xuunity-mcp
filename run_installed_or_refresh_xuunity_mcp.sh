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
elif [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  python_cmd=("$SCRIPT_DIR/.venv/bin/python")
elif [[ -x "$SCRIPT_DIR/.venv/bin/python3" ]]; then
  python_cmd=("$SCRIPT_DIR/.venv/bin/python3")
elif [[ -x "$SCRIPT_DIR/.venv/Scripts/python.exe" ]]; then
  python_cmd=("$SCRIPT_DIR/.venv/Scripts/python.exe")
elif command -v python3 >/dev/null 2>&1; then
  python_cmd=(python3)
elif command -v python >/dev/null 2>&1; then
  python_cmd=(python)
elif command -v py >/dev/null 2>&1; then
  python_cmd=(py -3)
else
  echo "Python 3 was not found. Install Python 3 or set PYTHON to its executable path." >&2
  printf 'launcher prerequisites: shell=%s version=%s python=not-found\n' "${BASH##*/}" "${BASH_VERSION:-unknown}" >&2
  exit 1
fi

XUUNITY_LIGHT_UNITY_MCP_BASH="${BASH:-}" \
XUUNITY_LIGHT_UNITY_MCP_SHELL_BASENAME="${BASH##*/}" \
XUUNITY_LIGHT_UNITY_MCP_SHELL_VERSION="${BASH_VERSION:-unknown}" \
XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME="${0##*/}" \
  exec "${python_cmd[@]}" "$SCRIPT_DIR/run_installed_or_refresh_xuunity_mcp.py" "$@"
