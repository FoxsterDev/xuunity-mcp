#!/usr/bin/env bash
set -euo pipefail

# Self-resolving install root. Works for any host install path (codex-tools,
# claude-tools, agent-agnostic, custom). Honors XUUNITY_LIGHT_UNITY_MCP_SERVER
# for explicit overrides.
script_source="${BASH_SOURCE[0]:-$0}"
script_dir="$(cd "$(dirname "$script_source")" && pwd -P)"
server_file="${XUUNITY_LIGHT_UNITY_MCP_SERVER:-$script_dir/server.py}"
export PYTHONUTF8="${PYTHONUTF8:-1}"

if [[ -n "${PYTHON:-}" ]]; then
  if [[ "$PYTHON" == "py -3" ]] && command -v py >/dev/null 2>&1; then
    python_cmd=(py -3)
  else
    python_cmd=("${PYTHON//\\//}")
  fi
elif [[ -x "$script_dir/.venv/bin/python" ]]; then
  python_cmd=("$script_dir/.venv/bin/python")
elif [[ -x "$script_dir/.venv/bin/python3" ]]; then
  python_cmd=("$script_dir/.venv/bin/python3")
elif [[ -x "$script_dir/.venv/Scripts/python" ]]; then
  python_cmd=("$script_dir/.venv/Scripts/python")
elif [[ -x "$script_dir/.venv/Scripts/python.exe" ]]; then
  python_cmd=("$script_dir/.venv/Scripts/python.exe")
elif command -v python3 >/dev/null 2>&1; then
  python_cmd=(python3)
elif command -v python >/dev/null 2>&1; then
  python_cmd=(python)
elif command -v py >/dev/null 2>&1; then
  python_cmd=(py -3)
else
  printf 'Python 3 was not found. Install Python 3.10+ or set PYTHON to its executable path.\n' >&2
  exit 1
fi

exec "${python_cmd[@]}" "$server_file" "$@"
