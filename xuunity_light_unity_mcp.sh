#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

source_root_has_mcp_package() {
  local candidate="$1"
  [[ -f "$candidate/templates/server.py" && -f "$candidate/packages/com.xuunity.light-mcp/package.json" ]]
}

resolve_source_root() {
  if [[ -n "${XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT:-}" ]]; then
    cd "$XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT" && pwd
    return 0
  fi

  if [[ -n "${XUUNITY_LIGHT_UNITY_MCP_AIRROOT:-}" ]]; then
    if source_root_has_mcp_package "$XUUNITY_LIGHT_UNITY_MCP_AIRROOT/Operations/XUUnityLightUnityMcp"; then
      cd "$XUUNITY_LIGHT_UNITY_MCP_AIRROOT/Operations/XUUnityLightUnityMcp" && pwd
      return 0
    fi
    if source_root_has_mcp_package "$XUUNITY_LIGHT_UNITY_MCP_AIRROOT"; then
      cd "$XUUNITY_LIGHT_UNITY_MCP_AIRROOT" && pwd
      return 0
    fi
  fi

  cd "$SCRIPT_DIR" && pwd
}

SOURCE_ROOT="$(resolve_source_root)"

CODEX_INSTALL_DIR="${CODEX_TOOLS_HOME:-$HOME/.codex-tools}/xuunity-mcp"
CLAUDE_INSTALL_DIR="${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}/xuunity-mcp"
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

NEUTRAL_INSTALL_DIR="$(resolve_neutral_install_dir)"


codex_context_detected() {
  [[ -n "${CODEX_SHELL:-}" ]] ||
    [[ -n "${CODEX_THREAD_ID:-}" ]] ||
    [[ -n "${CODEX_SANDBOX:-}" ]] ||
    [[ -n "${CODEX_HOME:-}" ]] ||
    [[ -n "${CODEX_CI:-}" ]] ||
    [[ "${CODEX_INTERNAL_ORIGINATOR_OVERRIDE:-}" == *Codex* ]]
}

claude_context_detected() {
  [[ -n "${CLAUDE_CODE:-}" ]] ||
    [[ -n "${CLAUDECODE:-}" ]] ||
    [[ -n "${CLAUDE_CONFIG_PATH:-}" ]]
}

resolve_install_dir() {
  local install_target="${XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET:-auto}"
  case "$install_target" in
    neutral)
      printf '%s\n' "$NEUTRAL_INSTALL_DIR"
      return 0
      ;;
    codex)
      printf '%s\n' "$CODEX_INSTALL_DIR"
      return 0
      ;;
    claude)
      printf '%s\n' "$CLAUDE_INSTALL_DIR"
      return 0
      ;;
    auto)
      if codex_context_detected; then
        printf '%s\n' "$CODEX_INSTALL_DIR"
        return 0
      fi
      if claude_context_detected; then
        printf '%s\n' "$CLAUDE_INSTALL_DIR"
        return 0
      fi
      if [[ -f "$NEUTRAL_INSTALL_DIR/server.py" ]]; then
        printf '%s\n' "$NEUTRAL_INSTALL_DIR"
        return 0
      fi
      if [[ -f "$CLAUDE_INSTALL_DIR/server.py" ]]; then
        printf '%s\n' "$CLAUDE_INSTALL_DIR"
        return 0
      fi
      if [[ -f "$CODEX_INSTALL_DIR/server.py" ]]; then
        printf '%s\n' "$CODEX_INSTALL_DIR"
        return 0
      fi
      printf '%s\n' "$NEUTRAL_INSTALL_DIR"
      return 0
      ;;
    *)
      echo "invalid XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET=$install_target (expected codex, claude, neutral, or auto)" >&2
      exit 1
      ;;
  esac
}

# Resolve the host install location agent-agnostically.
# Priority order:
#   1. XUUNITY_LIGHT_UNITY_MCP_SERVER explicit override
#   2. XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET=codex|claude|neutral explicit target
#   3. auto target: Codex context -> CODEX_TOOLS_HOME / ~/.codex-tools
#   4. auto target: Claude context -> CLAUDE_TOOLS_HOME / ~/.claude-tools
#   5. auto target: preserve existing helper when no client context is known (neutral, then Claude, then Codex)
#   6. NEUTRAL_INSTALL_DIR standard location (used as default fallback when nothing is installed)
if [[ -n "${XUUNITY_LIGHT_UNITY_MCP_SERVER:-}" ]]; then
  SERVER_PATH="$XUUNITY_LIGHT_UNITY_MCP_SERVER"
  INSTALL_DIR="$(cd "$(dirname "$SERVER_PATH")" && pwd)"
else
  INSTALL_DIR="$(resolve_install_dir)"
  SERVER_PATH="$INSTALL_DIR/server.py"
fi
RUN_PATH="$INSTALL_DIR/run.sh"
SERVER_TEMPLATE_RELATIVE_PATH="templates/server.py"
SOURCE_SERVER_PATH="$SOURCE_ROOT/$SERVER_TEMPLATE_RELATIVE_PATH"
RUN_TEMPLATE_RELATIVE_PATH="templates/run.sh"
SERVER_MODULES_TEMPLATE_RELATIVE_GLOB="templates/server_*.py"
RUNTIME_DEFAULTS_TEMPLATE_RELATIVE_PATH="templates/xuunity_light_unity_mcp_runtime_defaults.json"
PACKAGE_NAME="com.xuunity.light-mcp"
PACKAGE_TEMPLATE_RELATIVE_PATH="packages/com.xuunity.light-mcp"
PACKAGE_METADATA_RELATIVE_PATH="$PACKAGE_TEMPLATE_RELATIVE_PATH/package.json"
COMPACT_SUMMARY="false"

resolve_repo_root() {
  if [[ -n "${XUUNITY_LIGHT_UNITY_MCP_REPO_ROOT:-}" ]]; then
    cd "$XUUNITY_LIGHT_UNITY_MCP_REPO_ROOT" && pwd
    return 0
  fi

  local candidate
  for candidate in "$(cd "$SOURCE_ROOT/../../.." 2>/dev/null && pwd)" "$(cd "$SOURCE_ROOT/.." && pwd)"; do
    if [[ -d "$candidate/AIOutput" || -d "$candidate/AIModules" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  candidate="$(pwd)"
  while [[ "$candidate" != "/" ]]; do
    if [[ -d "$candidate/AIRoot" && ( -d "$candidate/AIOutput" || -d "$candidate/AIModules" ) ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
    candidate="$(dirname "$candidate")"
  done

  pwd
}

REPO_ROOT="$(resolve_repo_root)"
MINIMUM_PYTHON_VERSION="3.10"

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

exec_python() {
  if [[ "$PYTHON_ARGS_SET" == "1" ]]; then
    exec "$PYTHON_BIN" "${PYTHON_ARGS[@]}" "$@"
  else
    exec "$PYTHON_BIN" "$@"
  fi
}

python_version_supported() {
  python3 - "$MINIMUM_PYTHON_VERSION" <<'PY'
import re
import sys

minimum = tuple(int(item) for item in re.findall(r"\d+", sys.argv[1])[:2])
current = sys.version_info[:2]
raise SystemExit(0 if current >= minimum else 1)
PY
}

if ! python_version_supported; then
  current_python_version="$(python3 -c 'import sys; print(".".join(str(v) for v in sys.version_info[:3]))' 2>/dev/null || printf 'unknown')"
  printf 'Python %s or newer is required. Selected interpreter reports %s. Set PYTHON to a Python 3.10+ executable.\n' "$MINIMUM_PYTHON_VERSION" "$current_python_version" >&2
  exit 1
fi

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "required command not found: $command_name" >&2
    exit 1
  fi
}

require_package_source_root() {
  local expected_package_source="$SOURCE_ROOT/$PACKAGE_TEMPLATE_RELATIVE_PATH"
  if [[ -f "$SOURCE_ROOT/$SERVER_TEMPLATE_RELATIVE_PATH" && -f "$expected_package_source/package.json" ]]; then
    return 0
  fi

  echo "xuunity-mcp source root preflight failed" >&2
  echo "source_root=$SOURCE_ROOT" >&2
  echo "expected_package_source=$expected_package_source" >&2
  echo "airroot=${XUUNITY_LIGHT_UNITY_MCP_AIRROOT:-}" >&2
  echo "recommended_next_action=fix_source_root_or_set_XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT" >&2
  exit 1
}

emit_compact_summary_from_json_file() {
  local json_file="$1"
  local exit_code="$2"

  python3 - "$json_file" "$exit_code" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
exit_code = int(sys.argv[2])
if not path.is_file():
    raise SystemExit(0)
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
if not isinstance(payload, dict):
    raise SystemExit(0)

def line(*parts):
    sys.stderr.write("[xuunity-mcp] compact " + " ".join(str(p) for p in parts if str(p)) + "\n")

if str(payload.get("reason") or "") == "assistive_access_not_granted":
    line("outcome=window_arrangement", "reason=assistive_access_not_granted", "remediation=grant_accessibility_permission_then_rerun")
    raise SystemExit(0)

error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
error_code = str(error.get("code") or "")
if exit_code != 0 or error_code:
    parts = ["outcome=error", f"exit_code={exit_code}", f"code={error_code}"]
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    if payload.get("request_id"):
        parts.append(f"request_id={payload.get('request_id')}")
    next_action = payload.get("recommended_next_action") or error.get("recommended_next_action")
    if next_action:
        parts.append(f"next={next_action}")
    for key in (
        "process_visibility_error_code",
        "same_project_editor_closed",
        "process_exit_verified",
        "closeout_classification",
    ):
        value = payload.get(key)
        if value is None:
            value = details.get(key)
        if value is not None and value != "":
            if isinstance(value, bool):
                value = str(value).lower()
            parts.append(f"{key}={value}")
    line(*parts)
    raise SystemExit(0)

if payload.get("action") == "unity_status_summary" or "health_status" in payload:
    line(
        "outcome=status",
        f"health={payload.get('health_status', '')}",
        f"editor_running={str(bool(payload.get('editor_running'))).lower()}",
        f"mcp_reachable={str(bool(payload.get('mcp_reachable'))).lower()}",
        f"pending={int(payload.get('pending_request_count') or 0)}",
        f"busy_reason={payload.get('busy_reason', '')}",
        f"playmode={payload.get('playmode_state', '')}",
    )
    raise SystemExit(0)

if payload.get("action") == "unity_scenario_result_summary":
    parts = [
        "outcome=scenario",
        f"scenario={payload.get('scenario_name', '')}",
        f"status={payload.get('status', '')}",
        f"terminal={str(bool(payload.get('terminal'))).lower()}",
        f"passed_steps={int(payload.get('passed_steps') or 0)}",
        f"failed_steps={int(payload.get('failed_steps') or 0)}",
        f"skipped_steps={int(payload.get('skipped_steps') or 0)}",
    ]
    failed = payload.get("first_failed_step") if isinstance(payload.get("first_failed_step"), dict) else {}
    if failed:
        parts.append(f"first_failed={failed.get('step_id', '')}:{failed.get('error_code', '')}")
    profile = payload.get("profile_mutation_summary") if isinstance(payload.get("profile_mutation_summary"), dict) else {}
    if profile:
        parts.append(f"profile_restore_required={str(bool(profile.get('profile_restore_required'))).lower()}")
    line(*parts)
    raise SystemExit(0)

if payload.get("action") == "unity_project_action_invoke":
    parts = [
        "outcome=project_action",
        f"action_id={payload.get('action_id', '')}",
        f"hook={payload.get('hook_name', '')}",
        f"status={payload.get('status', '')}",
        f"succeeded={str(bool(payload.get('succeeded'))).lower()}",
        f"mutating={str(bool(payload.get('mutation'))).lower()}",
    ]
    if payload.get("result_path"):
        parts.append(f"result_path={payload.get('result_path')}")
    line(*parts)
    raise SystemExit(0)

if payload.get("action") == "unity_loading_timing_summary":
    parts = [
        "outcome=loading_timing",
        f"succeeded={str(bool(payload.get('succeeded'))).lower()}",
        f"matches={int(payload.get('match_count') or 0)}",
        f"returned={int(payload.get('returned_count') or 0)}",
        f"timing_values={int(payload.get('timing_value_count') or 0)}",
        f"truncated={str(bool(payload.get('truncated'))).lower()}",
    ]
    if payload.get("marker_count"):
        parts.append(f"markers={int(payload.get('marker_count') or 0)}")
    if payload.get("first_timestamp"):
        parts.append(f"first={payload.get('first_timestamp')}")
    if payload.get("last_timestamp"):
        parts.append(f"last={payload.get('last_timestamp')}")
    line(*parts)
    raise SystemExit(0)

if isinstance(payload.get("result_summary"), dict):
    summary = payload.get("result_summary") or {}
    matrix = summary.get("matrix") if isinstance(summary.get("matrix"), dict) else {}
    parts = [
        "outcome=batch",
        f"action={payload.get('action', '')}",
        f"succeeded={str(bool(payload.get('succeeded'))).lower()}",
        f"requested_lane={summary.get('requested_execution_lane', '')}",
        f"effective_lane={summary.get('effective_execution_lane', '')}",
        f"unity={summary.get('unity_outcome', '')}",
        f"transport={summary.get('transport_outcome', '')}",
    ]
    if matrix:
        parts.extend([
            f"matrix_status={matrix.get('status', '')}",
            f"total={int(matrix.get('total') or 0)}",
            f"failed={int(matrix.get('failed') or 0)}",
        ])
    if payload.get("summary_file"):
        parts.append(f"summary_file={payload.get('summary_file')}")
    line(*parts)
    raise SystemExit(0)

if payload.get("request_id") and payload.get("payload_type"):
    parts = [
        "outcome=ok",
        f"request_id={payload.get('request_id')}",
        f"payload_type={payload.get('payload_type')}",
        f"status={payload.get('status', '')}",
    ]
    decoded = {}
    raw = payload.get("payload_json")
    if isinstance(raw, str) and raw:
        try:
            decoded = json.loads(raw)
        except Exception:
            decoded = {}
    payload_type = str(payload.get("payload_type") or "")
    if payload_type == "unity.compile.matrix":
        parts.extend([
            f"matrix_status={decoded.get('status', '')}",
            f"total={int(decoded.get('total') or 0)}",
            f"passed={int(decoded.get('passed') or 0)}",
            f"failed={int(decoded.get('failed') or 0)}",
        ])
    elif payload_type.startswith("unity.tests."):
        parts.extend([
            f"test_status={decoded.get('status', '')}",
            f"total={int(decoded.get('total') or 0)}",
            f"passed={int(decoded.get('passed') or 0)}",
            f"failed={int(decoded.get('failed') or 0)}",
        ])
    elif payload_type == "unity.console.grep":
        parts.extend([
            f"matches={int(decoded.get('match_count') or 0)}",
            f"returned={len(decoded.get('items') or []) if isinstance(decoded.get('items'), list) else 0}",
            f"truncated={str(bool(decoded.get('truncated'))).lower()}",
        ])
    line(*parts)
PY
}

run_server_with_optional_compact_summary() {
  local server_path="$1"
  shift

  if [[ "$COMPACT_SUMMARY" != "true" ]]; then
    exec_python "$server_path" "$@"
  fi

  local stdout_file
  stdout_file="$(mktemp)"
  local exit_code=0

  if python3 "$server_path" "$@" >"$stdout_file"; then
    exit_code=0
  else
    exit_code=$?
  fi

  cat "$stdout_file"
  emit_compact_summary_from_json_file "$stdout_file" "$exit_code"
  rm -f "$stdout_file"
  return "$exit_code"
}

sync_file_from_source() {
  local destination_path="$1"
  local relative_source_path="$2"
  local temp_path
  temp_path="$(mktemp)"
  cp "$SOURCE_ROOT/$relative_source_path" "$temp_path"
  mkdir -p "$(dirname "$destination_path")"

  if [[ -f "$destination_path" ]] && cmp -s "$temp_path" "$destination_path"; then
    rm -f "$temp_path"
    return 0
  fi

  mv "$temp_path" "$destination_path"
}

sync_installed_helper_if_needed() {
  if [[ ! -e "$SOURCE_ROOT/.git" || ! -f "$SOURCE_ROOT/$SERVER_TEMPLATE_RELATIVE_PATH" ]]; then
    return 0
  fi

  mkdir -p "$INSTALL_DIR"

  sync_file_from_source "$SERVER_PATH" "$SERVER_TEMPLATE_RELATIVE_PATH"
  sync_file_from_source "$RUN_PATH" "$RUN_TEMPLATE_RELATIVE_PATH"
  sync_file_from_source "$INSTALL_DIR/$(basename "$RUNTIME_DEFAULTS_TEMPLATE_RELATIVE_PATH")" "$RUNTIME_DEFAULTS_TEMPLATE_RELATIVE_PATH"
  sync_file_from_source "$INSTALL_DIR/$PACKAGE_METADATA_RELATIVE_PATH" "$PACKAGE_METADATA_RELATIVE_PATH"

  local module_source_path=""
  for module_source_path in "$SOURCE_ROOT"/$SERVER_MODULES_TEMPLATE_RELATIVE_GLOB; do
    [[ -f "$module_source_path" ]] || continue
    sync_file_from_source "$INSTALL_DIR/$(basename "$module_source_path")" "${module_source_path#"$SOURCE_ROOT/"}"
  done
  chmod 755 "$RUN_PATH"
}

require_project_root_argument() {
  local project_root=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --project-root)
        shift
        if [[ $# -eq 0 ]]; then
          echo "--project-root requires a value" >&2
          exit 1
        fi
        project_root="$1"
        ;;
    esac
    shift || true
  done

  if [[ -z "$project_root" ]]; then
    echo "missing required argument: --project-root /path/to/UnityProject" >&2
    exit 1
  fi

  if [[ ! -d "$project_root/Packages" ]]; then
    echo "Unity project Packages directory not found under: $project_root" >&2
    exit 1
  fi

  python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$project_root"
}

normalize_git_url_for_unity_upm() {
  local git_url="$1"

  case "$git_url" in
    git@github.com:*)
      git_url="https://github.com/${git_url#git@github.com:}"
      ;;
    ssh://git@github.com/*)
      git_url="https://github.com/${git_url#ssh://git@github.com/}"
      ;;
  esac

  printf '%s\n' "$git_url"
}

remote_release_tag_commit() {
  local repo_root="$1"
  local remote_name="$2"
  local release_tag="$3"
  local tag_ref="refs/tags/$release_tag"
  local peeled_ref="${tag_ref}^{}"
  local hash=""
  local ref=""
  local direct_hash=""

  while IFS=$'\t' read -r hash ref; do
    if [[ "$ref" == "$peeled_ref" ]]; then
      printf '%s\n' "$hash"
      return 0
    fi
    if [[ "$ref" == "$tag_ref" ]]; then
      direct_hash="$hash"
    fi
  done < <(git -C "$repo_root" ls-remote --tags "$remote_name" "$tag_ref" "$peeled_ref")

  if [[ -n "$direct_hash" ]]; then
    printf '%s\n' "$direct_hash"
    return 0
  fi

  return 1
}

read_package_version() {
  python3 - "$SOURCE_ROOT/$PACKAGE_METADATA_RELATIVE_PATH" <<'PY'
import json
import pathlib
import sys

package_json = pathlib.Path(sys.argv[1])
version = json.loads(package_json.read_text(encoding="utf-8")).get("version", "")
if not version:
    raise SystemExit("Could not read package version from package.json")
print(version)
PY
}

read_project_unity_version() {
  local project_root="$1"
  python3 - "$project_root/ProjectSettings/ProjectVersion.txt" <<'PY'
import pathlib
import sys

project_version_path = pathlib.Path(sys.argv[1])
for line in project_version_path.read_text(encoding="utf-8").splitlines():
    if line.startswith("m_EditorVersion:"):
        print(line.split(":", 1)[1].strip())
        raise SystemExit(0)
raise SystemExit("Could not find m_EditorVersion in ProjectVersion.txt")
PY
}

update_manifest_dependency() {
  local manifest_path="$1"
  local dependency_value="$2"

  python3 - "$manifest_path" "$PACKAGE_NAME" "$dependency_value" <<'PY'
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
package_name = sys.argv[2]
dependency_value = sys.argv[3]

data = json.loads(manifest_path.read_text())
dependencies = data.setdefault("dependencies", {})
dependencies[package_name] = dependency_value
manifest_path.write_text(json.dumps(data, indent=2) + "\n")
PY
}

remove_lock_dependency() {
  local lock_path="$1"

  if [[ ! -f "$lock_path" ]]; then
    return 0
  fi

  python3 - "$lock_path" "$PACKAGE_NAME" <<'PY'
import json
import pathlib
import sys

lock_path = pathlib.Path(sys.argv[1])
package_name = sys.argv[2]

data = json.loads(lock_path.read_text())
dependencies = data.get("dependencies")
if isinstance(dependencies, dict) and package_name in dependencies:
    del dependencies[package_name]
    lock_path.write_text(json.dumps(data, indent=2) + "\n")
PY
}

switch_project_to_devmode() {

  local project_root
  project_root="$(require_project_root_argument "$@")"
  local manifest_path="$project_root/Packages/manifest.json"
  local lock_path="$project_root/Packages/packages-lock.json"
  local package_source_path="$SOURCE_ROOT/$PACKAGE_TEMPLATE_RELATIVE_PATH"

  require_package_source_root

  local dependency_value
  dependency_value="$(python3 - "$project_root/Packages" "$package_source_path" <<'PY'
import os
import sys
print("file:" + os.path.relpath(os.path.realpath(sys.argv[2]), os.path.realpath(sys.argv[1])))
PY
)"

  update_manifest_dependency "$manifest_path" "$dependency_value"
  remove_lock_dependency "$lock_path"

  echo "xuunity-mcp mode switched: devmode"
  echo "project_root=$project_root"
  echo "dependency=$dependency_value"
  echo "package_source=$package_source_path"
  echo "packages_lock_entry_removed=true"
  echo "next_step=let Unity re-resolve packages by reopen, focus, or explicit refresh"
}

switch_project_to_prodmode() {
  require_command git

  local project_root
  project_root="$(require_project_root_argument "$@")"
  local unity_version
  unity_version="$(read_project_unity_version "$project_root")"
  local unity_major="${unity_version%%.*}"

  require_package_source_root

  if [[ ! -e "$SOURCE_ROOT/.git" ]]; then
    echo "source git metadata not found: $SOURCE_ROOT/.git" >&2
    exit 1
  fi

  case "$unity_major" in
    6000|6[0-9][0-9][0-9])
      ;;
    *)
      echo "prodmode is currently supported only for Unity 6000+ package variants; use devmode for direct local package iteration on $unity_version" >&2
      exit 1
      ;;
  esac

  local manifest_path="$project_root/Packages/manifest.json"
  local lock_path="$project_root/Packages/packages-lock.json"
  local remote_name="origin"
  local git_url
  git_url="$(git -C "$SOURCE_ROOT" remote get-url "$remote_name")"
  git_url="$(normalize_git_url_for_unity_upm "$git_url")"
  local git_commit
  git_commit="$(git -C "$SOURCE_ROOT" rev-parse HEAD)"
  local source_branch
  source_branch="$(git -C "$SOURCE_ROOT" branch --show-current)"
  local package_version
  package_version="$(read_package_version)"
  local release_tag="v$package_version"
  local release_commit

  if ! release_commit="$(remote_release_tag_commit "$SOURCE_ROOT" "$remote_name" "$release_tag")"; then
    echo "prodmode requires the package release tag to be published on the remote before pinning it." >&2
    echo "release tag is not currently advertised by remote '$remote_name': $release_tag" >&2
    echo "Push it first, for example: git -C \"$SOURCE_ROOT\" push $remote_name $release_tag" >&2
    exit 1
  fi

  local dependency_value="${git_url}?path=/${PACKAGE_TEMPLATE_RELATIVE_PATH}#${release_tag}"

  update_manifest_dependency "$manifest_path" "$dependency_value"
  remove_lock_dependency "$lock_path"

  local worktree_dirty="false"
  if [[ -n "$(git -C "$SOURCE_ROOT" status --short)" ]]; then
    worktree_dirty="true"
  fi

  echo "xuunity-mcp mode switched: prodmode"
  echo "project_root=$project_root"
  echo "dependency=$dependency_value"
  echo "source_remote=$remote_name"
  echo "source_branch=$source_branch"
  echo "source_commit=$git_commit"
  echo "source_release_tag=$release_tag"
  echo "source_release_commit=$release_commit"
  if [[ "$git_commit" == "$release_commit" ]]; then
    echo "source_head_matches_release=true"
  else
    echo "source_head_matches_release=false"
  fi
  echo "source_worktree_dirty=$worktree_dirty"
  echo "packages_lock_entry_removed=true"
  if [[ "$worktree_dirty" == "true" ]]; then
    echo "warning=prodmode pins the published release tag; local working tree has unpublished changes"
  elif [[ "$git_commit" != "$release_commit" ]]; then
    echo "warning=prodmode pins the published release tag; local HEAD differs from the release commit"
  else
    echo "warning=prodmode pins the published release tag; Unity must re-resolve to apply it"
  fi
}

dispatch_arrange_unity_windows() {
  local arrange_script_path="$SOURCE_ROOT/scripts/tools/arrange_unity_windows.py"
  if [[ ! -f "$arrange_script_path" ]]; then
    echo "arrange_unity_windows.py not found: $arrange_script_path" >&2
    exit 1
  fi

  exec_python "$arrange_script_path" "$@"
}

print_wrapper_help() {
  cat <<EOF
Usage: $(basename "$0") [--compact-summary] <command> [args]

Wrapper commands:
  help | --help
      Show this wrapper command list.
  server-help
      Show the installed server CLI help.
  devmode --project-root PATH
      Point com.xuunity.light-mcp at the local packages/com.xuunity.light-mcp source
      and remove its package-lock entry so Unity can re-resolve it.
  prodmode --project-root PATH
      Pin com.xuunity.light-mcp to the published release tag matching the
      package version and remove its package-lock entry. Refuses missing
      release tags.
  arrange-unity-windows [args]
      Arrange Unity and agent windows on macOS.

Server commands:
  setup-plan, uninstall-plan, and uninstall-apply run from the source checkout
  and do not refresh or write the installed helper. Other server commands
  refresh the installed helper from this source checkout and delegate to
  server.py. Common commands include:
    setup-plan
    setup-apply
    uninstall-plan
    uninstall-apply
    validate-setup
    install-test-framework
    ensure-ready
    request-status-summary
    request-capabilities
    request-health-probe
    request-project-refresh
    request-console-grep
    request-loading-timing
    request-install-test-framework
    request-compile
    request-editmode-tests
    request-playmode-tests
    request-final-status
    restore-editor-state
    batch-compile
    batch-editmode-tests

Mode notes:
  devmode is for local MCP package iteration only.
  prodmode is for published release state only; push the package release tag
  before switching a project back to prodmode.
  After devmode or prodmode, let Unity re-resolve packages by reopen, focus, or
  explicit project refresh.
EOF
}

print_mode_help() {
  local mode="$1"
  case "$mode" in
    devmode)
      cat <<EOF
Usage: $(basename "$0") devmode --project-root PATH

Switch a Unity project to local XUUnity Light Unity MCP package development.

Effects:
  - sets com.xuunity.light-mcp to file:<relative path to packages/com.xuunity.light-mcp>
  - removes the com.xuunity.light-mcp package-lock entry

After switching, let Unity re-resolve packages by reopen, focus, or explicit
project refresh before running validation.
EOF
      ;;
    prodmode)
      cat <<EOF
Usage: $(basename "$0") prodmode --project-root PATH

Switch a Unity project to a published Git release-tagged XUUnity Light Unity MCP package.

Effects:
  - verifies the package release tag is advertised by the remote
  - sets com.xuunity.light-mcp to the remote Git package URL pinned to that tag
  - removes the com.xuunity.light-mcp package-lock entry

Push the package release tag before prodmode. After switching, let Unity
re-resolve packages by reopen, focus, or explicit project refresh before running
validation.
EOF
      ;;
  esac
}

filtered_args=()
for arg in "$@"; do
  if [[ "$arg" == "--compact-summary" ]]; then
    COMPACT_SUMMARY="true"
    continue
  fi
  filtered_args+=("$arg")
done
set -- "${filtered_args[@]}"

case "${1:-}" in
  -h|--help|help)
    print_wrapper_help
    exit 0
    ;;
esac

case "${1:-}" in
  setup-plan)
    shift
    if [[ ! -f "$SOURCE_SERVER_PATH" ]]; then
      echo "xuunity-mcp source server not found: $SOURCE_SERVER_PATH" >&2
      exit 1
    fi
    run_server_with_optional_compact_summary "$SOURCE_SERVER_PATH" setup-plan "$@"
    exit 0
    ;;
  uninstall-plan)
    shift
    if [[ ! -f "$SOURCE_SERVER_PATH" ]]; then
      echo "xuunity-mcp source server not found: $SOURCE_SERVER_PATH" >&2
      exit 1
    fi
    run_server_with_optional_compact_summary "$SOURCE_SERVER_PATH" uninstall-plan "$@"
    exit 0
    ;;
  uninstall-apply)
    shift
    if [[ ! -f "$SOURCE_SERVER_PATH" ]]; then
      echo "xuunity-mcp source server not found: $SOURCE_SERVER_PATH" >&2
      exit 1
    fi
    run_server_with_optional_compact_summary "$SOURCE_SERVER_PATH" uninstall-apply "$@"
    exit 0
    ;;
  server-help)
    shift
    sync_installed_helper_if_needed
    run_server_with_optional_compact_summary "$SERVER_PATH" --help "$@"
    exit 0
    ;;
  arrange-unity-windows)
    shift
    dispatch_arrange_unity_windows "$@"
    exit 0
    ;;
  devmode)
    shift
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
      print_mode_help devmode
      exit 0
    fi
    switch_project_to_devmode "$@"
    exit 0
    ;;
  prodmode)
    shift
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
      print_mode_help prodmode
      exit 0
    fi
    switch_project_to_prodmode "$@"
    exit 0
    ;;
esac

sync_installed_helper_if_needed

if [[ ! -f "$SERVER_PATH" ]]; then
  echo "xuunity-mcp server not found: $SERVER_PATH" >&2
  echo "Install it with: bash init_xuunity_light_unity_mcp.sh" >&2
  exit 1
fi

run_server_with_optional_compact_summary "$SERVER_PATH" "$@"
