#!/usr/bin/env bash
set -euo pipefail

dry_run=0
force=0
install_codex_config=0
install_claude_config=0
enable_project=0
disable_project=0
uninstall_project=0
project_root=""
target="both"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root)
      project_root="$2"
      shift 2
      ;;
    --install-codex-config)
      install_codex_config=1
      shift
      ;;
    --install-claude-config)
      install_claude_config=1
      shift
      ;;
    --target)
      target="$2"
      case "$target" in
        codex|claude|both|neutral) ;;
        *)
          echo "Unknown --target value: $target (allowed: codex, claude, both, neutral)" >&2
          exit 1
          ;;
      esac
      shift 2
      ;;
    --enable-project)
      enable_project=1
      shift
      ;;
    --disable-project)
      disable_project=1
      shift
      ;;
    --uninstall-project)
      uninstall_project=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --force)
      force=1
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  bash init_xuunity_light_unity_mcp.sh [options]

Options:
    --project-root <path>     Optional Unity project root for enabling or disabling the editor-only bridge under Library/.
  --target codex|claude|both|neutral  Choose which install location(s) receive the server files.
                              codex   -> \$CODEX_TOOLS_HOME/xuunity-mcp  (default \$HOME/.codex-tools)
                              claude  -> \$CLAUDE_TOOLS_HOME/xuunity-mcp (default \$HOME/.claude-tools)
                              neutral -> \$HOME/.xuunity-mcp
                              both    -> install into both. Default: both.
  --install-codex-config      Also append the Codex MCP config block.
  --install-claude-config     Also register the MCP server in ~/.claude.json (Claude Code user scope).
  --enable-project          Write local bridge config under Library/ so the editor-only bridge is active on next editor load.
  --disable-project         Remove local bridge config and local bridge state under Library/.
  --uninstall-project       Remove the manifest dependency and local bridge state from the Unity project.
  --dry-run                 Print intended actions without writing files.
  --force                   Overwrite installed scaffold files.
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

script_dir="$(cd "$(dirname "$0")" && pwd)"
templates_dir="$script_dir/templates"
package_metadata_source="$script_dir/packages/com.xuunity.light-mcp/package.json"
minimum_python_version="3.10"
codex_home="${CODEX_HOME:-$HOME/.codex}"
codex_tools_home="${CODEX_TOOLS_HOME:-$HOME/.codex-tools}"
claude_tools_home="${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}"
codex_install_dir="$codex_tools_home/xuunity-mcp"
claude_install_dir="$claude_tools_home/xuunity-mcp"
config_path="$codex_home/config.toml"
claude_config_path="${CLAUDE_CONFIG_PATH:-$HOME/.claude.json}"
codex_run_path="$codex_install_dir/run.sh"
claude_run_path="$claude_install_dir/run.sh"
resolve_neutral_install_dir() {
  if [[ -n "${XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR:-}" ]]; then
    printf '%s\n' "$XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"
    return 0
  fi

  if [[ "${OS:-}" == "Windows_NT" ]] || [[ -n "${APPDATA:-}" ]]; then
    local appdata_val="${APPDATA:-}"
    if [[ -z "$appdata_val" ]]; then
      appdata_val="$HOME/AppData/Roaming"
    fi
    printf '%s/xuunity-mcp\n' "${appdata_val//\\//}"
    return 0
  fi

  local xdg_val="${XDG_DATA_HOME:-}"
  if [[ -n "$xdg_val" ]]; then
    printf '%s/xuunity-mcp\n' "$xdg_val"
    return 0
  fi

  local uname_sys
  uname_sys="$(uname -s 2>/dev/null || echo "unknown")"
  if [[ "$uname_sys" == "Darwin" ]]; then
    printf '%s/Library/Application Support/xuunity-mcp\n' "$HOME"
  else
    printf '%s/.local/share/xuunity-mcp\n' "$HOME"
  fi
}

neutral_install_dir="$(resolve_neutral_install_dir)"
neutral_run_path="$neutral_install_dir/run.sh"


resolve_python_bin() {
  if [[ -n "${PYTHON:-}" ]]; then
    if [[ "$PYTHON" == "py -3" ]] && command -v py >/dev/null 2>&1; then
      command -v py
      return 0
    fi
    if [[ "$PYTHON" != */* && "$PYTHON" != *" "* ]] && command -v "$PYTHON" >/dev/null 2>&1; then
      command -v "$PYTHON"
      return 0
    fi
    printf '%s\n' "$PYTHON"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  if command -v py >/dev/null 2>&1; then
    command -v py
    return 0
  fi
  echo "Python 3 was not found. Install Python 3 or set PYTHON to its executable path." >&2
  exit 1
}

PYTHON_BIN="$(resolve_python_bin)"
PYTHON_ARGS=()
PYTHON_ARGS_SET=0
case "$(basename "$PYTHON_BIN" | tr '[:upper:]' '[:lower:]')" in
  py|py.exe)
    PYTHON_ARGS=(-3)
    PYTHON_ARGS_SET=1
    ;;
esac

python3() {
  if [[ "$PYTHON_ARGS_SET" == "1" ]]; then
    "$PYTHON_BIN" "${PYTHON_ARGS[@]}" "$@"
  else
    "$PYTHON_BIN" "$@"
  fi
}

python_version_supported() {
  python3 - "$minimum_python_version" <<'PY'
import re
import sys

minimum = tuple(int(item) for item in re.findall(r"\d+", sys.argv[1])[:2])
current = sys.version_info[:2]
raise SystemExit(0 if current >= minimum else 1)
PY
}

if ! python_version_supported; then
  current_python_version="$(python3 -c 'import sys; print(".".join(str(v) for v in sys.version_info[:3]))' 2>/dev/null || printf 'unknown')"
  printf 'Python %s or newer is required. Selected interpreter reports %s. Set PYTHON to a Python 3.10+ executable.\n' "$minimum_python_version" "$current_python_version" >&2
  exit 1
fi

run() {
  if [[ $dry_run -eq 1 ]]; then
    printf '[dry-run] %s' "$1"
    shift
    for arg in "$@"; do
      printf ' %q' "$arg"
    done
    printf '\n'
  else
    "$@"
  fi
}

copy_if_needed() {
  local src="$1"
  local dst="$2"
  local mode="$3"

  if [[ -f "$dst" && $force -ne 1 ]] && cmp -s "$src" "$dst"; then
    printf 'kept existing %s\n' "$dst"
    return
  fi

  run cp "$src" "$dst"
  run chmod "$mode" "$dst"
  printf 'installed %s\n' "$dst"
}

warn_ripgrep_fallback_once() {
  if [[ "${xuunity_light_unity_mcp_rg_fallback_warned:-0}" -eq 1 ]]; then
    return 0
  fi
  printf '%s\n' 'optional command not found: rg; using grep fallback. Install ripgrep for faster local checks: brew install ripgrep' >&2
  xuunity_light_unity_mcp_rg_fallback_warned=1
}

file_contains_regex() {
  local pattern="$1"
  local file_path="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -q "$pattern" "$file_path"
  else
    warn_ripgrep_fallback_once
    grep -Eq "$pattern" "$file_path"
  fi
}

append_codex_block_if_missing() {
  local block
  local codex_run_path_val="$codex_run_path"
  if [[ "$target" == "neutral" ]]; then
    codex_run_path_val="$neutral_run_path"
  fi
  block=$'[mcp_servers.xuunity_light_unity]\n'
  block+=$'command = "bash"\n'
  block+="args = [\"-lc\", \"exec \\\"$codex_run_path_val\\\"\"]"$'\n'
  block+=$'required = false\n'

  if [[ -f "$config_path" ]] && file_contains_regex '^\[mcp_servers\.xuunity_light_unity\]' "$config_path"; then
    printf 'kept existing MCP config in %s\n' "$config_path"
    return
  fi

  if [[ $dry_run -eq 1 ]]; then
    printf '[dry-run] append MCP block to %s\n' "$config_path"
    printf '%s' "$block"
    return
  fi

  mkdir -p "$codex_home"
  touch "$config_path"
  if [[ -s "$config_path" ]]; then
    printf '\n' >> "$config_path"
  fi
  printf '%s' "$block" >> "$config_path"
  printf 'updated %s\n' "$config_path"
}

append_claude_block_if_missing() {
  local claude_run_path_val="$claude_run_path"
  if [[ "$target" == "neutral" ]]; then
    claude_run_path_val="$neutral_run_path"
  fi

  if [[ $dry_run -eq 1 ]]; then
    printf '[dry-run] register xuunity_light_unity MCP server in %s\n' "$claude_config_path"
    return
  fi

  mkdir -p "$(dirname "$claude_config_path")"

  python3 - "$claude_config_path" "$claude_run_path_val" <<'PY'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
run_path = sys.argv[2]

if config_path.exists() and config_path.stat().st_size > 0:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"refusing to modify malformed JSON at {config_path}", file=sys.stderr)
        raise SystemExit(2)
else:
    data = {}

if not isinstance(data, dict):
    print(f"refusing to modify non-object JSON at {config_path}", file=sys.stderr)
    raise SystemExit(2)

servers = data.setdefault("mcpServers", {})
existing = servers.get("xuunity_light_unity")

portable_run_command = f'exec "{run_path}"'
desired = {
    "type": "stdio",
    "command": "bash",
    "args": ["-lc", portable_run_command],
}

if existing == desired:
    print(f"kept existing Claude MCP config in {config_path}")
    raise SystemExit(0)

servers["xuunity_light_unity"] = desired
config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(f"updated {config_path}")
PY
}

patch_manifest_if_needed() {
  local manifest_path="$1"
  local package_source_path="$2"

  if [[ $dry_run -eq 1 ]]; then
    printf '[dry-run] patch manifest %s with com.xuunity.light-mcp file dependency -> %s\n' "$manifest_path" "$package_source_path"
    return
  fi

  python3 - "$manifest_path" "$package_source_path" <<'PY'
import json
import os
import sys

manifest_path = sys.argv[1]
package_source_path = sys.argv[2]
with open(manifest_path, "r", encoding="utf-8") as fh:
    data = json.load(fh)

deps = data.setdefault("dependencies", {})
manifest_dir = os.path.dirname(manifest_path)
relative_package_source_path = os.path.relpath(package_source_path, start=manifest_dir).replace(os.sep, "/")
value = "file:" + relative_package_source_path
if deps.get("com.xuunity.light-mcp") != value:
    deps["com.xuunity.light-mcp"] = value
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=True)
        fh.write("\n")
PY

  printf 'updated %s\n' "$manifest_path"
}

unpatch_manifest_if_needed() {
  local manifest_path="$1"

  if [[ $dry_run -eq 1 ]]; then
    printf '[dry-run] remove com.xuunity.light-mcp dependency from %s\n' "$manifest_path"
    return
  fi

  python3 - "$manifest_path" <<'PY'
import json
import sys

manifest_path = sys.argv[1]
with open(manifest_path, "r", encoding="utf-8") as fh:
    data = json.load(fh)

deps = data.get("dependencies", {})
deps.pop("com.xuunity.light-mcp", None)

with open(manifest_path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, ensure_ascii=True)
    fh.write("\n")
PY

  printf 'updated %s\n' "$manifest_path"
}

write_bridge_config() {
  local project_root="$1"
  local config_dir="$project_root/Library/XUUnityLightMcp/config"
  local config_path="$config_dir/bridge_config.json"

  if [[ $dry_run -eq 1 ]]; then
    printf '[dry-run] write %s\n' "$config_path"
    return
  fi

  mkdir -p "$config_dir"
  cat > "$config_path" <<'EOF'
{
  "enabled": true,
  "heartbeat_interval_ms": 2000,
  "pump_interval_ms": 500,
  "transport": "tcp_loopback",
  "loopback_host": "127.0.0.1",
  "loopback_port": 0
}
EOF
  printf 'updated %s\n' "$config_path"
}

remove_bridge_state() {
  local project_root="$1"
  local bridge_root="$project_root/Library/XUUnityLightMcp"

  if [[ ! -e "$bridge_root" ]]; then
    return
  fi

  if [[ $dry_run -eq 1 ]]; then
    printf '[dry-run] remove %s\n' "$bridge_root"
    return
  fi

  rm -rf "$bridge_root"
  printf 'removed %s\n' "$bridge_root"
}

setup_venv_if_needed() {
  local target_dir="$1"
  local venv_dir="$target_dir/.venv"

  if [[ $dry_run -eq 1 ]]; then
    printf '[dry-run] set up Python virtual environment in %s/.venv\n' "$target_dir"
    return 0
  fi

  if [[ -d "$venv_dir" ]]; then
    if [[ -x "$venv_dir/bin/python" ]] || [[ -x "$venv_dir/bin/python3" ]] || [[ -x "$venv_dir/Scripts/python.exe" ]]; then
      return 0
    fi
  fi

  printf 'Setting up Python virtual environment in %s/.venv...\n' "$target_dir"
  run mkdir -p "$target_dir"

  if ! python3 -m venv "$venv_dir" >/dev/null 2>&1; then
    printf 'Warning: "python -m venv" failed. Falling back to direct script execution without isolated venv.\n' >&2
    return 0
  fi

  local venv_python=""
  if [[ -x "$venv_dir/bin/python" ]]; then
    venv_python="$venv_dir/bin/python"
  elif [[ -x "$venv_dir/bin/python3" ]]; then
    venv_python="$venv_dir/bin/python3"
  elif [[ -x "$venv_dir/Scripts/python.exe" ]]; then
    venv_python="$venv_dir/Scripts/python.exe"
  fi

  if [[ -n "$venv_python" ]]; then
    "$venv_python" -m pip install --upgrade pip >/dev/null 2>&1 || true
  fi
}

install_server_into() {
  local target_dir="$1"
  run mkdir -p "$target_dir"
  setup_venv_if_needed "$target_dir"
  copy_if_needed "$templates_dir/server.py" "$target_dir/server.py" 644
  for helper_module in "$templates_dir"/server_*.py; do
    [[ -f "$helper_module" ]] || continue
    copy_if_needed "$helper_module" "$target_dir/$(basename "$helper_module")" 644
  done
  copy_if_needed "$templates_dir/run.sh" "$target_dir/run.sh" 755
  copy_if_needed "$templates_dir/run.cmd" "$target_dir/run.cmd" 644
  copy_if_needed "$templates_dir/run.ps1" "$target_dir/run.ps1" 644
  run mkdir -p "$target_dir/packages/com.xuunity.light-mcp"
  copy_if_needed "$package_metadata_source" "$target_dir/packages/com.xuunity.light-mcp/package.json" 644
}

install_delegates_into() {
  local target_dir="$1"
  local neutral_dir="$2"
  run mkdir -p "$target_dir"

  # Write delegate run.sh
  if [[ $dry_run -eq 1 ]]; then
    printf '[dry-run] write delegate run.sh to %s/run.sh\n' "$target_dir"
  else
    cat > "$target_dir/run.sh" <<EOF
#!/usr/bin/env bash
exec "$neutral_dir/run.sh" "\$@"
EOF
    chmod 755 "$target_dir/run.sh"
  fi

  # Write delegate run.cmd
  if [[ $dry_run -eq 1 ]]; then
    printf '[dry-run] write delegate run.cmd to %s/run.cmd\n' "$target_dir"
  else
    cat > "$target_dir/run.cmd" <<EOF
@echo off
call "$neutral_dir\run.cmd" %*
EOF
    chmod 644 "$target_dir/run.cmd"
  fi

  # Write delegate run.ps1
  if [[ $dry_run -eq 1 ]]; then
    printf '[dry-run] write delegate run.ps1 to %s/run.ps1\n' "$target_dir"
  else
    cat > "$target_dir/run.ps1" <<EOF
& "$neutral_dir\run.ps1" @args
EOF
    chmod 644 "$target_dir/run.ps1"
  fi

  # Write delegate server.py
  if [[ $dry_run -eq 1 ]]; then
    printf '[dry-run] write delegate server.py to %s/server.py\n' "$target_dir"
  else
    cat > "$target_dir/server.py" <<EOF
import os
import sys
import platform

neutral_dir = os.path.expanduser("$neutral_dir")
central_server = os.path.join(neutral_dir, "server.py")

system = platform.system().lower()
if system == "windows":
    venv_python = os.path.join(neutral_dir, ".venv", "Scripts", "python.exe")
else:
    venv_python = os.path.join(neutral_dir, ".venv", "bin", "python")

if os.path.isfile(venv_python) and os.access(venv_python, os.X_OK):
    python_bin = venv_python
else:
    python_bin = sys.executable

os.execv(python_bin, [python_bin, central_server] + sys.argv[1:])
EOF
    chmod 644 "$target_dir/server.py"
  fi
}

run mkdir -p "$codex_home"
# Always install full server files to the neutral directory
install_server_into "$neutral_install_dir"

case "$target" in
  codex)
    install_delegates_into "$codex_install_dir" "$neutral_install_dir"
    ;;
  claude)
    install_delegates_into "$claude_install_dir" "$neutral_install_dir"
    ;;
  both)
    install_delegates_into "$codex_install_dir" "$neutral_install_dir"
    install_delegates_into "$claude_install_dir" "$neutral_install_dir"
    ;;
  neutral)
    # Core server is already installed in neutral_install_dir
    ;;
esac

if [[ -n "$project_root" ]]; then
  project_root="$(cd "$project_root" && pwd)"
  if [[ ! -d "$project_root/Assets" || ! -f "$project_root/ProjectSettings/ProjectVersion.txt" ]]; then
    echo "Not a Unity project root: $project_root" >&2
    exit 1
  fi

  manifest_path="$project_root/Packages/manifest.json"

  if [[ $uninstall_project -eq 1 ]]; then
    unpatch_manifest_if_needed "$manifest_path"
    remove_bridge_state "$project_root"
  elif [[ $disable_project -eq 1 ]]; then
    remove_bridge_state "$project_root"
  else
    if [[ $enable_project -eq 1 ]]; then
      write_bridge_config "$project_root"
    fi
  fi
fi

if [[ $install_codex_config -eq 1 ]]; then
  append_codex_block_if_missing
  printf 'note: restart the current Codex client session if it does not hot-reload newly installed MCP servers.\n'
else
  printf 'skipped Codex config install by default; use --install-codex-config to register the stdio MCP server in a real client.\n'
fi

if [[ $install_claude_config -eq 1 ]]; then
  append_claude_block_if_missing
else
  printf 'skipped Claude Code user-scope config install by default; use --install-claude-config to register the server in ~/.claude.json, or copy templates/clients/claude-code/.mcp.json into a repo for project scope.\n'
fi

smoke_install_dir="$neutral_install_dir"

cat <<EOF

Next steps:
1. If you passed --project-root with --enable-project, open or reopen the Unity project once so the editor-only bridge can start writing heartbeat state.
2. Smoke-check bridge state:
   python3 $smoke_install_dir/server.py bridge-state --project-root /path/to/UnityProject
3. Smoke-check the direct same-host request status path:
   python3 $smoke_install_dir/server.py request-status --project-root /path/to/UnityProject
4. Preferred interactive startup helper:
   python3 $smoke_install_dir/server.py ensure-ready --project-root /path/to/UnityProject --open-editor --background-open --startup-policy fail_fast_on_interactive_compile_block

Installed files:
EOF

case "$target" in
  codex)
    printf -- '- %s/server.py\n- %s/run.sh\n- %s/run.cmd\n- %s/run.ps1\n' "$codex_install_dir" "$codex_install_dir" "$codex_install_dir" "$codex_install_dir"
    ;;
  claude)
    printf -- '- %s/server.py\n- %s/run.sh\n- %s/run.cmd\n- %s/run.ps1\n' "$claude_install_dir" "$claude_install_dir" "$claude_install_dir" "$claude_install_dir"
    ;;
  both)
    printf -- '- %s/server.py\n- %s/run.sh\n- %s/run.cmd\n- %s/run.ps1\n- %s/server.py\n- %s/run.sh\n- %s/run.cmd\n- %s/run.ps1\n' \
      "$codex_install_dir" "$codex_install_dir" "$codex_install_dir" "$codex_install_dir" \
      "$claude_install_dir" "$claude_install_dir" "$claude_install_dir" "$claude_install_dir"
    ;;
esac
