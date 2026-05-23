#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OPS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WRAPPER="$OPS_ROOT/xuunity_light_unity_mcp.sh"
INIT_SCRIPT="$OPS_ROOT/init_xuunity_light_unity_mcp.sh"
BUILD_HELPER_TEMPLATE="$SCRIPT_DIR/assets/AndroidBuildSmoke.cs"
PACKAGE_MANIFEST="$OPS_ROOT/packages/com.xuunity.light-mcp/package.json"

ARTIFACT_ROOT="${XUUNITY_LIGHT_UNITY_MCP_ANDROID_SMOKE_ROOT:-${TMPDIR:-/tmp}/xuunity-light-unity-mcp-android-smoke}"
RUN_ID="$(date -u '+%Y%m%dT%H%M%SZ')"
RUN_ROOT="$ARTIFACT_ROOT/$RUN_ID"
DEFAULT_PROJECT_ROOT="$RUN_ROOT/projects/XUUnityLightMcpAndroidSmoke"
DEFAULT_APK_PATH="$RUN_ROOT/artifacts/xuunity-light-unity-mcp-android-smoke.apk"
DEFAULT_BUILD_LOG="$RUN_ROOT/logs/android_build.log"
DEFAULT_CREATE_LOG="$RUN_ROOT/logs/create_project.log"
SUMMARY_JSON="$RUN_ROOT/summary.json"
GRADLE_APK_OUTPUT_RELATIVE_PATH="Library/Bee/Android/Prj/IL2CPP/Gradle/launcher/build/outputs/apk/release/launcher-release.apk"

UNITY_PATH=""
PROJECT_ROOT=""
PACKAGE_MODE="git"
ALLOW_NO_ANDROID="false"
KEEP_PROJECT="false"
RECREATE_PROJECT="false"
OPEN_EDITOR="true"
RESTORE_EDITOR_STATE="true"
TIMEOUT_MS="180000"
BUILD_TIMEOUT_MS="900000"
APK_OUTPUT_PATH=""
CREATE_LOG_PATH=""
BUILD_LOG_PATH=""
TMP_DIR=""
HOST_INSTALL_OUTPUT_FILE=""
ENABLE_PROJECT_OUTPUT_FILE=""
ENSURE_READY_OUTPUT_FILE=""
STATUS_SUMMARY_OUTPUT_FILE=""
RESTORE_EDITOR_OUTPUT_FILE=""
ANDROID_PLAYER_INSTALLED="false"
ANDROID_PLAYER_PATH=""
OVERALL_RESULT="pending"
FAILURE_STAGE=""
BUILD_STATUS="pending"
BUILD_STATUS_REASON=""
RECOMMENDED_ACTION=""

usage() {
  cat <<EOF
Usage:
  $(basename "$0") [options]

Options:
  --unity-path <path>         Unity executable path. Defaults to latest installed editor with AndroidPlayer support.
  --project-root <path>       Unity project root to create or reuse. Default: $DEFAULT_PROJECT_ROOT
  --artifact-root <path>      Artifact root. Default: $ARTIFACT_ROOT
  --package-mode git|devmode  Package source mode. Default: git
  --allow-no-android          Continue with MCP-only smoke when Android Build Support is missing; mark APK build as skipped.
  --keep-project              Keep the generated Unity project after the run.
  --recreate-project          Recreate the project root even if it already exists.
  --no-open-editor            Skip --open-editor during ensure-ready.
  --no-restore-editor-state   Do not close the host-opened editor before batch build.
  --timeout-ms <ms>           ensure-ready / status timeout. Default: $TIMEOUT_MS
  --build-timeout-ms <ms>     Batch Android build timeout. Default: $BUILD_TIMEOUT_MS
  -h, --help                  Show this help.
EOF
}

fail_usage() {
  echo "$1" >&2
  usage >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --unity-path)
      shift
      [[ $# -gt 0 ]] || fail_usage "--unity-path requires a value"
      UNITY_PATH="$1"
      ;;
    --project-root)
      shift
      [[ $# -gt 0 ]] || fail_usage "--project-root requires a value"
      PROJECT_ROOT="$1"
      ;;
    --artifact-root)
      shift
      [[ $# -gt 0 ]] || fail_usage "--artifact-root requires a value"
      ARTIFACT_ROOT="$1"
      ;;
    --package-mode)
      shift
      [[ $# -gt 0 ]] || fail_usage "--package-mode requires a value"
      PACKAGE_MODE="$1"
      ;;
    --allow-no-android)
      ALLOW_NO_ANDROID="true"
      ;;
    --keep-project)
      KEEP_PROJECT="true"
      ;;
    --recreate-project)
      RECREATE_PROJECT="true"
      ;;
    --no-open-editor)
      OPEN_EDITOR="false"
      ;;
    --no-restore-editor-state)
      RESTORE_EDITOR_STATE="false"
      ;;
    --timeout-ms)
      shift
      [[ $# -gt 0 ]] || fail_usage "--timeout-ms requires a value"
      TIMEOUT_MS="$1"
      ;;
    --build-timeout-ms)
      shift
      [[ $# -gt 0 ]] || fail_usage "--build-timeout-ms requires a value"
      BUILD_TIMEOUT_MS="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail_usage "Unknown argument: $1"
      ;;
  esac
  shift
done

case "$PACKAGE_MODE" in
  git|devmode)
    ;;
  *)
    fail_usage "Unsupported --package-mode: $PACKAGE_MODE"
    ;;
esac

ARTIFACT_ROOT="$(python3 - "$ARTIFACT_ROOT" <<'PY'
import os
import sys

path = sys.argv[1]
parent = os.path.dirname(path) or "."
parent_real = os.path.realpath(parent)
print(os.path.join(parent_real, os.path.basename(path)))
PY
)"

RUN_ROOT="$ARTIFACT_ROOT/$RUN_ID"
DEFAULT_PROJECT_ROOT="$RUN_ROOT/projects/XUUnityLightMcpAndroidSmoke"
DEFAULT_APK_PATH="$RUN_ROOT/artifacts/xuunity-light-unity-mcp-android-smoke.apk"
DEFAULT_BUILD_LOG="$RUN_ROOT/logs/android_build.log"
DEFAULT_CREATE_LOG="$RUN_ROOT/logs/create_project.log"
SUMMARY_JSON="$RUN_ROOT/summary.json"

PROJECT_ROOT="${PROJECT_ROOT:-$DEFAULT_PROJECT_ROOT}"
PROJECT_ROOT="$(python3 - "$PROJECT_ROOT" <<'PY'
import os
import sys

path = sys.argv[1]
parent = os.path.dirname(path) or "."
parent_real = os.path.realpath(parent)
print(os.path.join(parent_real, os.path.basename(path)))
PY
)"
APK_OUTPUT_PATH="${APK_OUTPUT_PATH:-$DEFAULT_APK_PATH}"
CREATE_LOG_PATH="${CREATE_LOG_PATH:-$DEFAULT_CREATE_LOG}"
BUILD_LOG_PATH="${BUILD_LOG_PATH:-$DEFAULT_BUILD_LOG}"
GRADLE_APK_OUTPUT_PATH="$PROJECT_ROOT/$GRADLE_APK_OUTPUT_RELATIVE_PATH"

TMP_DIR="$(mktemp -d)"
HOST_INSTALL_OUTPUT_FILE="$TMP_DIR/init_host.txt"
ENABLE_PROJECT_OUTPUT_FILE="$TMP_DIR/init_project.txt"
ENSURE_READY_OUTPUT_FILE="$TMP_DIR/ensure_ready.json"
STATUS_SUMMARY_OUTPUT_FILE="$TMP_DIR/status_summary.json"
RESTORE_EDITOR_OUTPUT_FILE="$TMP_DIR/restore_editor_state.json"

cleanup() {
  if [[ "$RESTORE_EDITOR_STATE" == "true" && -f "$ENSURE_READY_OUTPUT_FILE" ]]; then
    "$WRAPPER" restore-editor-state \
      --project-root "$PROJECT_ROOT" \
      --timeout-ms 30000 >"$RESTORE_EDITOR_OUTPUT_FILE" 2>/dev/null || true
  fi
  if [[ "$KEEP_PROJECT" != "true" && "$PROJECT_ROOT" == "$DEFAULT_PROJECT_ROOT" ]]; then
    rm -rf "$PROJECT_ROOT"
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

fail() {
  echo "$1" >&2
  exit 1
}

write_summary_json() {
  python3 - "$SUMMARY_JSON" \
    "$RUN_ID" \
    "$UNITY_PATH" \
    "$PROJECT_ROOT" \
    "$PACKAGE_MODE" \
    "$MANIFEST_DEPENDENCY" \
    "$ALLOW_NO_ANDROID" \
    "$ANDROID_PLAYER_INSTALLED" \
    "$ANDROID_PLAYER_PATH" \
    "$OVERALL_RESULT" \
    "$FAILURE_STAGE" \
    "$BUILD_STATUS" \
    "$BUILD_STATUS_REASON" \
    "$RECOMMENDED_ACTION" \
    "$APK_OUTPUT_PATH" \
    "$CREATE_LOG_PATH" \
    "$BUILD_LOG_PATH" \
    "$HOST_INSTALL_OUTPUT_FILE" \
    "$ENABLE_PROJECT_OUTPUT_FILE" \
    "$ENSURE_READY_OUTPUT_FILE" \
    "$STATUS_SUMMARY_OUTPUT_FILE" \
    "$RESTORE_EDITOR_OUTPUT_FILE" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

def read_json_if_present(path_text: str):
    path = Path(path_text)
    if not path.is_file() or path.stat().st_size == 0:
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def sha256_if_present(path_text: str):
    path = Path(path_text)
    if not path.is_file():
        return "", 0
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), path.stat().st_size

summary_path = Path(sys.argv[1])
run_id = sys.argv[2]
unity_path = sys.argv[3]
project_root = sys.argv[4]
package_mode = sys.argv[5]
manifest_dependency = sys.argv[6]
allow_no_android = sys.argv[7] == "true"
android_player_installed = sys.argv[8] == "true"
android_player_path = sys.argv[9]
overall_result = sys.argv[10]
failure_stage = sys.argv[11]
build_status = sys.argv[12]
build_status_reason = sys.argv[13]
recommended_action = sys.argv[14]
apk_path = sys.argv[15]
create_log = sys.argv[16]
build_log = sys.argv[17]
host_install_output = sys.argv[18]
enable_project_output = sys.argv[19]
ensure_ready_output = read_json_if_present(sys.argv[20])
status_summary_output = read_json_if_present(sys.argv[21])
restore_payload = read_json_if_present(sys.argv[22])
apk_sha256, apk_size_bytes = sha256_if_present(apk_path)

payload = {
    "run_id": run_id,
    "result": overall_result,
    "failure_stage": failure_stage,
    "recommended_action": recommended_action,
    "unity_path": unity_path,
    "project_root": project_root,
    "package_mode": package_mode,
    "manifest_dependency": manifest_dependency,
    "preflight": {
        "allow_no_android": allow_no_android,
        "android_player_installed": android_player_installed,
        "android_player_path": android_player_path,
    },
    "ensure_ready": None,
    "status_summary": None,
    "restore_editor_state": restore_payload,
    "build": {
        "status": build_status,
        "reason": build_status_reason,
    },
    "apk": {
        "path": apk_path,
        "sha256": apk_sha256,
        "size_bytes": apk_size_bytes,
    },
    "logs": {
        "create_project": create_log,
        "build": build_log,
    },
    "installer_outputs": {
        "host_install": host_install_output,
        "enable_project": enable_project_output,
    },
}

if ensure_ready_output is not None:
    payload["ensure_ready"] = {
        "bridge_version": ensure_ready_output.get("bridge_state", {}).get("bridge_version"),
        "health_status": ensure_ready_output.get("bridge_state", {}).get("health_status"),
        "playmode_state": ensure_ready_output.get("bridge_state", {}).get("playmode_state"),
    }

if status_summary_output is not None:
    payload["status_summary"] = {
        "editor_running": status_summary_output.get("editor_running"),
        "mcp_reachable": status_summary_output.get("mcp_reachable"),
        "health_status": status_summary_output.get("health_status"),
        "transport": status_summary_output.get("transport"),
        "dependency_mode": status_summary_output.get("host_prerequisites", {}).get("checks", {}).get("package_dependency", {}).get("dependency_mode"),
        "alignment": status_summary_output.get("host_prerequisites", {}).get("checks", {}).get("package_dependency", {}).get("alignment"),
        "warning_codes": status_summary_output.get("host_prerequisites", {}).get("warning_codes", []),
    }

summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || fail "Required file not found: $path"
}

detect_latest_unity_editor() {
  local mode="$1"
  python3 - "$mode" <<'PY'
import os
import sys
from pathlib import Path

root = Path("/Applications/Unity/Hub/Editor")
if not root.is_dir():
    raise SystemExit(1)

def version_key(text: str):
    import re
    match = re.match(r"(\d+)\.(\d+)\.(\d+)([A-Za-z])(\d+)$", text)
    if not match:
        return (0, 0, 0, 0, 0, text)
    stream_rank = {"a": 0, "b": 1, "f": 2, "p": 3, "x": 4}
    major, minor, patch, stream, build = match.groups()
    return (int(major), int(minor), int(patch), stream_rank.get(stream.lower(), 99), int(build), text)

candidates = []
mode = sys.argv[1]
for child in root.iterdir():
    unity = child / "Unity.app" / "Contents" / "MacOS" / "Unity"
    android_candidates = [
        child / "PlaybackEngines" / "AndroidPlayer",
        child / "Unity.app" / "Contents" / "PlaybackEngines" / "AndroidPlayer",
    ]
    android_installed = any(path.is_dir() for path in android_candidates)
    if unity.is_file() and (mode == "any" or android_installed):
        candidates.append((version_key(child.name), str(unity.resolve())))

if not candidates:
    raise SystemExit(1)

candidates.sort()
print(candidates[-1][1])
PY
}

inspect_android_player_support() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path

unity_path = Path(sys.argv[1]).expanduser().resolve()
android_candidates = []

if unity_path.name == "Unity" and unity_path.parent.name == "MacOS" and unity_path.parent.parent.name == "Contents":
    contents_dir = unity_path.parent.parent
    app_dir = contents_dir.parent
    version_dir = app_dir.parent
    android_candidates = [
        version_dir / "PlaybackEngines" / "AndroidPlayer",
        contents_dir / "PlaybackEngines" / "AndroidPlayer",
    ]
else:
    android_candidates = [
        unity_path.parent / "PlaybackEngines" / "AndroidPlayer",
        unity_path.parent.parent / "PlaybackEngines" / "AndroidPlayer",
    ]

resolved = ""
for candidate in android_candidates:
    if candidate.is_dir():
        resolved = str(candidate.resolve())
        break

print(json.dumps({
    "unity_path": str(unity_path),
    "android_player_installed": bool(resolved),
    "android_player_path": resolved,
}, indent=2))
PY
}

if [[ -z "$UNITY_PATH" ]]; then
  if UNITY_PATH="$(detect_latest_unity_editor android 2>/dev/null)"; then
    :
  elif [[ "$ALLOW_NO_ANDROID" == "true" ]]; then
    UNITY_PATH="$(detect_latest_unity_editor any 2>/dev/null)" || fail "Could not auto-detect any installed Unity editor. Pass --unity-path explicitly."
  else
    UNITY_PATH="$(detect_latest_unity_editor any 2>/dev/null || true)"
  fi
fi

require_file "$UNITY_PATH"
require_file "$BUILD_HELPER_TEMPLATE"
require_file "$PACKAGE_MANIFEST"

ANDROID_SUPPORT_JSON="$(inspect_android_player_support "$UNITY_PATH")"
ANDROID_PLAYER_INSTALLED="$(python3 - <<'PY' "$ANDROID_SUPPORT_JSON"
import json
import sys
print("true" if json.loads(sys.argv[1]).get("android_player_installed") else "false")
PY
)"
ANDROID_PLAYER_PATH="$(python3 - <<'PY' "$ANDROID_SUPPORT_JSON"
import json
import sys
print(str(json.loads(sys.argv[1]).get("android_player_path") or ""))
PY
)"

if [[ "$ANDROID_PLAYER_INSTALLED" != "true" ]]; then
  BUILD_STATUS="skipped_missing_android_build_support"
  BUILD_STATUS_REASON="Android Build Support (PlaybackEngines/AndroidPlayer) is not installed for the selected Unity editor."
  RECOMMENDED_ACTION="Install Android Build Support for this Unity version through Unity Hub, choose a Unity editor with AndroidPlayer support, or rerun with --allow-no-android for MCP-only smoke."
  if [[ "$ALLOW_NO_ANDROID" != "true" ]]; then
    OVERALL_RESULT="failed_preflight"
    FAILURE_STAGE="preflight"
    MANIFEST_DEPENDENCY=""
    mkdir -p "$RUN_ROOT/logs" "$RUN_ROOT/artifacts" "$(dirname "$PROJECT_ROOT")"
    write_summary_json
    fail "Android Build Support is not installed for $UNITY_PATH. See $SUMMARY_JSON"
  fi
fi

PACKAGE_VERSION="$(python3 - "$PACKAGE_MANIFEST" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(str(payload.get("version") or "").strip())
PY
)"
[[ -n "$PACKAGE_VERSION" ]] || fail "Could not resolve package version from $PACKAGE_MANIFEST"
GIT_PACKAGE_DEPENDENCY="https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/packages/com.xuunity.light-mcp#v$PACKAGE_VERSION"

mkdir -p "$RUN_ROOT/logs" "$RUN_ROOT/artifacts" "$(dirname "$PROJECT_ROOT")"

create_project() {
  if [[ -d "$PROJECT_ROOT/Assets" && "$RECREATE_PROJECT" != "true" ]]; then
    return 0
  fi

  rm -rf "$PROJECT_ROOT"
  "$UNITY_PATH" \
    -batchmode \
    -quit \
    -createProject "$PROJECT_ROOT" \
    -logFile "$CREATE_LOG_PATH"
}

set_git_dependency() {
  local manifest_path="$PROJECT_ROOT/Packages/manifest.json"
  python3 - "$manifest_path" "$GIT_PACKAGE_DEPENDENCY" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
dependency_value = sys.argv[2]
payload = json.loads(manifest_path.read_text(encoding="utf-8"))
payload.setdefault("dependencies", {})["com.xuunity.light-mcp"] = dependency_value
manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

clear_package_lock_entry() {
  local lock_path="$PROJECT_ROOT/Packages/packages-lock.json"
  [[ -f "$lock_path" ]] || return 0
  python3 - "$lock_path" <<'PY'
import json
import sys
from pathlib import Path

lock_path = Path(sys.argv[1])
payload = json.loads(lock_path.read_text(encoding="utf-8"))
dependencies = payload.get("dependencies")
if isinstance(dependencies, dict) and "com.xuunity.light-mcp" in dependencies:
    del dependencies["com.xuunity.light-mcp"]
    lock_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

install_build_helper() {
  local editor_dir="$PROJECT_ROOT/Assets/Editor"
  mkdir -p "$editor_dir"
  cp "$BUILD_HELPER_TEMPLATE" "$editor_dir/AndroidBuildSmoke.cs"
}

assert_manifest_mode() {
  local expected_mode="$1"
  python3 - "$PROJECT_ROOT/Packages/manifest.json" "$expected_mode" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
value = str(manifest.get("dependencies", {}).get("com.xuunity.light-mcp") or "")
expected = sys.argv[2]
if expected == "git":
    ok = value.startswith("https://") and "?path=/packages/com.xuunity.light-mcp#" in value
else:
    ok = value.startswith("file:")
if not ok:
    raise SystemExit(1)
print(value)
PY
}

hash_file_sha256() {
  python3 - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
digest = hashlib.sha256()
with path.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
}

run_json_command() {
  local output_file="$1"
  shift
  "$@" >"$output_file"
}

build_success_signals_present() {
  [[ -f "$APK_OUTPUT_PATH" || -f "$GRADLE_APK_OUTPUT_PATH" ]] || return 1
  [[ -f "$BUILD_LOG_PATH" ]] || return 1
  if rg -q "Build Finished, Result: Success\\.|Android smoke build result: Succeeded|ExitCode: 0 Duration:" "$BUILD_LOG_PATH"; then
    return 0
  fi
  return 1
}

kill_process_tree_if_running() {
  local pid="$1"
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi
  pkill -TERM -P "$pid" >/dev/null 2>&1 || true
  kill "$pid" >/dev/null 2>&1 || true
}

create_project
set_git_dependency
clear_package_lock_entry
install_build_helper

bash "$INIT_SCRIPT" >"$HOST_INSTALL_OUTPUT_FILE"
bash "$INIT_SCRIPT" --project-root "$PROJECT_ROOT" --enable-project >"$ENABLE_PROJECT_OUTPUT_FILE"

if [[ "$PACKAGE_MODE" == "devmode" ]]; then
  bash "$WRAPPER" devmode --project-root "$PROJECT_ROOT" >/dev/null
fi

MANIFEST_DEPENDENCY="$(assert_manifest_mode "$PACKAGE_MODE")" || fail "Package mode assertion failed after project setup."

ensure_ready_cmd=(
  bash "$WRAPPER" ensure-ready
  --project-root "$PROJECT_ROOT"
  --timeout-ms "$TIMEOUT_MS"
)
if [[ "$OPEN_EDITOR" == "true" ]]; then
  ensure_ready_cmd+=(--open-editor)
fi
run_json_command "$ENSURE_READY_OUTPUT_FILE" "${ensure_ready_cmd[@]}"

run_json_command \
  "$STATUS_SUMMARY_OUTPUT_FILE" \
  bash "$WRAPPER" request-status-summary \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms "$TIMEOUT_MS"

if [[ "$RESTORE_EDITOR_STATE" == "true" ]]; then
  run_json_command \
    "$RESTORE_EDITOR_OUTPUT_FILE" \
    bash "$WRAPPER" restore-editor-state \
    --project-root "$PROJECT_ROOT" \
    --timeout-ms 30000
fi

if [[ "$ANDROID_PLAYER_INSTALLED" != "true" ]]; then
  OVERALL_RESULT="passed_with_android_skipped"
  FAILURE_STAGE=""
  write_summary_json
  echo "[android-apk-smoke] passed with Android build skipped"
  echo "[android-apk-smoke] reason=$BUILD_STATUS_REASON"
  echo "[android-apk-smoke] summary=$SUMMARY_JSON"
  echo "[android-apk-smoke] project_root=$PROJECT_ROOT"
  echo "[android-apk-smoke] package_mode=$PACKAGE_MODE"
  exit 0
fi

XUUNITY_SMOKE_APK_PATH="$APK_OUTPUT_PATH" \
  "$UNITY_PATH" \
  -batchmode \
  -quit \
  -projectPath "$PROJECT_ROOT" \
  -buildTarget Android \
  -executeMethod AndroidBuildSmoke.BuildAndroidApk \
  -logFile "$BUILD_LOG_PATH" &
build_pid=$!

deadline=$(( $(date +%s) + (BUILD_TIMEOUT_MS / 1000) ))
success_grace_started_at=""
while kill -0 "$build_pid" >/dev/null 2>&1; do
  if (( $(date +%s) >= deadline )); then
    kill_process_tree_if_running "$build_pid"
    wait "$build_pid" || true
    fail "Android batch build timed out after ${BUILD_TIMEOUT_MS} ms. See $BUILD_LOG_PATH"
  fi

  if build_success_signals_present; then
    if [[ -z "$success_grace_started_at" ]]; then
      success_grace_started_at="$(date +%s)"
    elif (( $(date +%s) - success_grace_started_at >= 15 )); then
      kill_process_tree_if_running "$build_pid"
      wait "$build_pid" || true
      break
    fi
  fi
  sleep 1
done
wait "$build_pid"

if [[ ! -f "$APK_OUTPUT_PATH" && -f "$GRADLE_APK_OUTPUT_PATH" ]]; then
  cp "$GRADLE_APK_OUTPUT_PATH" "$APK_OUTPUT_PATH"
fi

[[ -f "$APK_OUTPUT_PATH" ]] || fail "APK not found after build: $APK_OUTPUT_PATH"
OVERALL_RESULT="passed"
FAILURE_STAGE=""
BUILD_STATUS="passed"
BUILD_STATUS_REASON=""
write_summary_json

echo "[android-apk-smoke] passed"
echo "[android-apk-smoke] summary=$SUMMARY_JSON"
echo "[android-apk-smoke] project_root=$PROJECT_ROOT"
echo "[android-apk-smoke] package_mode=$PACKAGE_MODE"
echo "[android-apk-smoke] apk=$APK_OUTPUT_PATH"
