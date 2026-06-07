#!/usr/bin/env bash
set -euo pipefail

# Self-resolving install root. Works for any host install path (codex-tools,
# claude-tools, agent-agnostic, custom). Honors XUUNITY_LIGHT_UNITY_MCP_SERVER
# for explicit overrides.
script_source="${BASH_SOURCE[0]:-$0}"
script_dir="$(cd "$(dirname "$script_source")" && pwd -P)"
server_file="${XUUNITY_LIGHT_UNITY_MCP_SERVER:-$script_dir/server.py}"
minimum_python_version="3.10"

python_version_is_supported() {
  "$1" - "$minimum_python_version" <<'PY'
import re
import sys

minimum = tuple(int(item) for item in re.findall(r"\d+", sys.argv[1])[:2])
current = sys.version_info[:2]
raise SystemExit(0 if current >= minimum else 1)
PY
}

if [[ -n "${PYTHON:-}" ]]; then
  python_cmd=("$PYTHON")
elif command -v python3 >/dev/null 2>&1; then
  python_cmd=(python3)
elif command -v python >/dev/null 2>&1; then
  python_cmd=(python)
elif command -v py >/dev/null 2>&1; then
  python_cmd=(py -3)
else
  printf 'Python 3 was not found. Install Python 3 or set PYTHON to its executable path.\n' >&2
  exit 1
fi

if ! python_version_is_supported "${python_cmd[0]}"; then
  current_version="$("${python_cmd[@]}" -c 'import sys; print(".".join(str(v) for v in sys.version_info[:3]))' 2>/dev/null || printf 'unknown')"
  printf 'Python %s or newer is required. Selected interpreter reports %s. Set PYTHON to a Python 3.10+ executable.\n' "$minimum_python_version" "$current_version" >&2
  exit 1
fi

exec "${python_cmd[@]}" "$server_file" "$@"
