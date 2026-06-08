#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_ROOT="${XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
WRAPPER_PATH="${XUUNITY_LIGHT_UNITY_MCP_WRAPPER:-$SOURCE_ROOT/xuunity_light_unity_mcp.sh}"

PARALLELISM=4
CLOSE_LIVE_EDITORS="true"
KEEP_RESULTS="true"
BATCH_FALLBACK_MODE="auto"
RESULTS_DIR=""
PROJECT_ROOTS=()

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

usage() {
  cat <<'EOF'
Usage:
  run_multi_project_batch_compile_matrix.sh [options]

Options:
  --parallelism N          Number of concurrent batch compile workers. Default: 4
  --repo-root PATH         Root containing Unity project directories. Defaults to env or current repo layout.
  --project-root PATH      Include one explicit Unity project root. Repeatable.
  --close-live-editors     Try to recover/close live editors before batch compile. Default.
  --no-close-live-editors  Skip the recovery preflight and fail fast on editor conflicts.
  --batch-fallback-mode M  Batch lane fallback policy: auto, off, or require-batch. Default: auto.
  --results-dir DIR        Write status artifacts to a persistent directory.
  --cleanup-results        Remove the results dir on exit instead of keeping it.
  --help                   Show this message.

Behavior:
  - auto-discovers direct child Unity projects under the selected repo root
  - filters to projects that already declare com.xuunity.light-mcp
  - runs batch-build-config-compile-matrix in parallel
  - prefers real Unity batchmode and uses GUI fallback when --batch-fallback-mode auto allows it
  - emits one compact per-project summary plus a final aggregate summary
  - keeps results_dir by default so it can feed later GUI-subset runs
EOF
}

resolve_project_root() {
  local candidate="$1"
  if [[ ! -d "$candidate" ]]; then
    candidate="$REPO_ROOT/$candidate"
  fi
  if [[ ! -d "$candidate" ]]; then
    echo "Project root not found: $1" >&2
    exit 1
  fi
  python3 - "$candidate" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).resolve())
PY
}

warn_ripgrep_fallback_once() {
  if [[ "${XUUNITY_LIGHT_UNITY_MCP_RG_FALLBACK_WARNED:-false}" == "true" ]]; then
    return 0
  fi
  echo "optional command not found: rg; using grep fallback. Install ripgrep for faster local checks: brew install ripgrep" >&2
  XUUNITY_LIGHT_UNITY_MCP_RG_FALLBACK_WARNED="true"
}

manifest_declares_light_mcp() {
  local manifest_path="$1"
  if command -v rg >/dev/null 2>&1; then
    rg -q '"com\.xuunity\.light-mcp"' "$manifest_path"
  else
    warn_ripgrep_fallback_once
    grep -Eq '"com\.xuunity\.light-mcp"' "$manifest_path"
  fi
}

discover_project_roots() {
  local child_dir=""
  for child_dir in "$REPO_ROOT"/*; do
    [[ -d "$child_dir" ]] || continue
    [[ -f "$child_dir/Packages/manifest.json" ]] || continue
    [[ -f "$child_dir/ProjectSettings/ProjectVersion.txt" ]] || continue
    if manifest_declares_light_mcp "$child_dir/Packages/manifest.json"; then
      printf '%s\n' "$child_dir"
    fi
  done | sort
}

run_worker() {
  local results_dir="$1"
  local close_live_editors="$2"
  local batch_fallback_mode="$3"
  local project_root="$4"
  local project_name
  project_name="$(basename "$project_root")"
  local worker_prefix="$results_dir/$project_name"
  local recover_output_file="${worker_prefix}_recover.log"
  local stdout_file="${worker_prefix}_batch_stdout.json"
  local stderr_file="${worker_prefix}_batch_stderr.log"
  local status_file="${worker_prefix}_status.json"
  local recover_rc=0
  local batch_rc=0

  if [[ "$close_live_editors" == "true" ]]; then
    if "$WRAPPER_PATH" recover-editor-session --project-root "$project_root" >"$recover_output_file" 2>&1; then
      :
    else
      recover_rc=$?
    fi
  fi

  if "$WRAPPER_PATH" batch-build-config-compile-matrix --project-root "$project_root" --batch-fallback-mode "$batch_fallback_mode" >"$stdout_file" 2>"$stderr_file"; then
    :
  else
    batch_rc=$?
  fi

  python3 - "$project_name" "$project_root" "$stdout_file" "$stderr_file" "$status_file" "$recover_rc" "$batch_rc" "$batch_fallback_mode" <<'PY'
import json
import sys
from pathlib import Path

project_name = sys.argv[1]
project_root = sys.argv[2]
stdout_file = Path(sys.argv[3])
stderr_file = Path(sys.argv[4])
status_file = Path(sys.argv[5])
recover_rc = int(sys.argv[6])
batch_rc = int(sys.argv[7])
invoked_batch_fallback_mode = sys.argv[8]

payload = {}
parse_error = ""
if stdout_file.is_file():
    text = stdout_file.read_text(encoding="utf-8")
    try:
        decoder = json.JSONDecoder()
        idx = 0
        last_obj = None
        while idx < len(text):
            tail = text[idx:]
            stripped = tail.lstrip()
            if not stripped:
                break
            skipped = len(tail) - len(stripped)
            obj, end = decoder.raw_decode(stripped)
            last_obj = obj
            idx += skipped + end
        if isinstance(last_obj, dict):
            payload = last_obj
        elif last_obj is None:
            parse_error = "no JSON document found on stdout"
        else:
            parse_error = f"unexpected JSON root type: {type(last_obj).__name__}"
    except Exception as exc:
        parse_error = str(exc)

result_summary = payload.get("result_summary") if isinstance(payload, dict) else {}
matrix = result_summary.get("matrix") if isinstance(result_summary, dict) else {}
stderr_tail = ""
if stderr_file.is_file():
    stderr_lines = stderr_file.read_text(encoding="utf-8", errors="replace").splitlines()
    stderr_tail = "\n".join(stderr_lines[-20:])

def first_string(*values):
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text:
            return text
    return ""

requested_execution_lane = first_string(
    result_summary.get("requested_execution_lane") if isinstance(result_summary, dict) else "",
    payload.get("requested_execution_lane") if isinstance(payload, dict) else "",
    "batch",
)
effective_execution_lane = first_string(
    result_summary.get("effective_execution_lane") if isinstance(result_summary, dict) else "",
    payload.get("effective_execution_lane") if isinstance(payload, dict) else "",
)
batch_fallback_mode = first_string(
    result_summary.get("batch_fallback_mode") if isinstance(result_summary, dict) else "",
    payload.get("batch_fallback_mode") if isinstance(payload, dict) else "",
    invoked_batch_fallback_mode,
)
lane_fallback_reason = first_string(
    result_summary.get("lane_fallback_reason") if isinstance(result_summary, dict) else "",
    payload.get("lane_fallback_reason") if isinstance(payload, dict) else "",
)
license_blocker_code = first_string(
    result_summary.get("license_blocker_code") if isinstance(result_summary, dict) else "",
    payload.get("license_blocker_code") if isinstance(payload, dict) else "",
)
unity_outcome = first_string(result_summary.get("unity_outcome") if isinstance(result_summary, dict) else "")
transport_outcome = first_string(result_summary.get("transport_outcome") if isinstance(result_summary, dict) else "")
matrix_status = first_string(matrix.get("status") if isinstance(matrix, dict) else "")
gui_fallback_pass = (
    bool(payload.get("succeeded")) if isinstance(payload, dict) else False
) and unity_outcome == "passed" and transport_outcome == "gui_operation_completed" and effective_execution_lane == "gui"
batch_matrix_pass = matrix_status == "passed" and effective_execution_lane in {"", "batch"}

if recover_rc == 0 and batch_rc == 0 and bool(payload.get("succeeded")) and batch_matrix_pass and int(matrix.get("failed", 0)) == 0:
    operator_verdict = "passed_via_batch"
elif recover_rc == 0 and batch_rc == 0 and gui_fallback_pass:
    operator_verdict = "passed_via_gui_fallback"
elif unity_outcome in {"not_started", ""} and (batch_rc != 0 or transport_outcome.endswith("_blocked") or effective_execution_lane == "none"):
    operator_verdict = "failed_before_unity"
elif unity_outcome and unity_outcome != "passed":
    operator_verdict = "failed_in_unity"
else:
    operator_verdict = "failed_wrapper_unity_unproven"

status = {
    "project": project_name,
    "project_root": project_root,
    "recover_rc": recover_rc,
    "batch_rc": batch_rc,
    "json_parse_ok": bool(payload),
    "parse_error": parse_error,
    "succeeded": bool(payload.get("succeeded")) if isinstance(payload, dict) else False,
    "requested_execution_lane": requested_execution_lane,
    "effective_execution_lane": effective_execution_lane,
    "batch_fallback_mode": batch_fallback_mode,
    "lane_fallback_reason": lane_fallback_reason,
    "license_blocker_code": license_blocker_code,
    "operator_verdict": operator_verdict,
    "unity_outcome": unity_outcome,
    "transport_outcome": transport_outcome,
    "matrix_status": matrix_status,
    "total": int(matrix.get("total", 0)) if isinstance(matrix, dict) else 0,
    "passed": int(matrix.get("passed", 0)) if isinstance(matrix, dict) else 0,
    "failed": int(matrix.get("failed", 0)) if isinstance(matrix, dict) else 0,
    "skipped": int(matrix.get("skipped", 0)) if isinstance(matrix, dict) else 0,
    "summary_file": str(payload.get("summary_file", "")) if isinstance(payload, dict) else "",
    "result_file": str(payload.get("result_file", "")) if isinstance(payload, dict) else "",
    "log_path": str(payload.get("log_path", "")) if isinstance(payload, dict) else "",
    "stderr_tail": stderr_tail,
}

status_file.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
PY
}

emit_final_summary() {
  local results_dir="$1"
  python3 - "$results_dir" <<'PY'
import json
import sys
from pathlib import Path

results_dir = Path(sys.argv[1])
status_files = sorted(results_dir.glob("*_status.json"))
statuses = [json.loads(path.read_text(encoding="utf-8")) for path in status_files]

print("MULTI_PROJECT_BATCH_COMPILE_MATRIX_SUMMARY_BEGIN")
overall_failed = 0
verdict_counts = {}
for item in statuses:
    gui_fallback_pass = (
        item.get("succeeded") is True
        and item.get("unity_outcome") == "passed"
        and item.get("transport_outcome") == "gui_operation_completed"
        and item.get("effective_execution_lane") == "gui"
    )
    operator_verdict = str(item.get("operator_verdict") or "")
    if not operator_verdict:
        if item.get("matrix_status") == "passed" and item.get("failed", 0) == 0:
            operator_verdict = "passed_via_batch"
        elif gui_fallback_pass:
            operator_verdict = "passed_via_gui_fallback"
        elif item.get("unity_outcome") in {"not_started", ""}:
            operator_verdict = "failed_before_unity"
        elif item.get("unity_outcome") and item.get("unity_outcome") != "passed":
            operator_verdict = "failed_in_unity"
        else:
            operator_verdict = "failed_wrapper_unity_unproven"
    verdict_counts[operator_verdict] = verdict_counts.get(operator_verdict, 0) + 1
    ok = (
        item.get("recover_rc", 0) == 0
        and item.get("batch_rc", 0) == 0
        and item.get("succeeded") is True
        and (item.get("matrix_status") == "passed" or gui_fallback_pass)
        and item.get("failed", 0) == 0
    )
    if not ok:
        overall_failed += 1
    fields = [
        item.get("project", ""),
        f"recover_rc={item.get('recover_rc', 0)}",
        f"batch_rc={item.get('batch_rc', 0)}",
        f"succeeded={str(bool(item.get('succeeded'))).lower()}",
        f"verdict={operator_verdict}",
        f"requested_lane={item.get('requested_execution_lane', '')}",
        f"effective_lane={item.get('effective_execution_lane', '')}",
        f"fallback_mode={item.get('batch_fallback_mode', '')}",
        f"fallback_reason={item.get('lane_fallback_reason', '')}",
        f"license_blocker={item.get('license_blocker_code', '')}",
        f"transport={item.get('transport_outcome', '')}",
        f"unity={item.get('unity_outcome', '')}",
        f"matrix_status={item.get('matrix_status', '')}",
        f"total={item.get('total', 0)}",
        f"passed={item.get('passed', 0)}",
        f"failed={item.get('failed', 0)}",
        f"skipped={item.get('skipped', 0)}",
        f"result_file={item.get('result_file', '')}",
    ]
    print("|".join(fields))
print("MULTI_PROJECT_BATCH_COMPILE_MATRIX_SUMMARY_END")

aggregate = {
    "projects_total": len(statuses),
    "projects_failed": overall_failed,
    "operator_verdict_counts": verdict_counts,
    "results_dir": str(results_dir),
}
print(json.dumps(aggregate, indent=2))
if overall_failed:
    raise SystemExit(1)
PY
}

if [[ "${1:-}" == "__worker__" ]]; then
  run_worker "$2" "$3" "$4" "$5"
  exit 0
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --parallelism)
      PARALLELISM="${2:-}"
      shift 2
      ;;
    --repo-root)
      REPO_ROOT="$(cd "${2:-}" && pwd)"
      shift 2
      ;;
    --project-root)
      PROJECT_ROOTS+=("$(resolve_project_root "${2:-}")")
      shift 2
      ;;
    --close-live-editors)
      CLOSE_LIVE_EDITORS="true"
      shift
      ;;
    --no-close-live-editors)
      CLOSE_LIVE_EDITORS="false"
      shift
      ;;
    --batch-fallback-mode)
      BATCH_FALLBACK_MODE="${2:-}"
      shift 2
      ;;
    --results-dir)
      RESULTS_DIR="$2"
      shift 2
      ;;
    --cleanup-results)
      KEEP_RESULTS="false"
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ! "$PARALLELISM" =~ ^[0-9]+$ ]] || [[ "$PARALLELISM" -lt 1 ]]; then
  echo "parallelism must be a positive integer" >&2
  exit 1
fi

case "$BATCH_FALLBACK_MODE" in
  auto|off|require-batch)
    ;;
  *)
    echo "batch fallback mode must be one of: auto, off, require-batch" >&2
    exit 1
    ;;
esac

if [[ ! -x "$WRAPPER_PATH" ]]; then
  echo "Wrapper not found or not executable: $WRAPPER_PATH" >&2
  exit 1
fi

if [[ ${#PROJECT_ROOTS[@]} -eq 0 ]]; then
  while IFS= read -r project_root; do
    [[ -n "$project_root" ]] || continue
    PROJECT_ROOTS+=("$project_root")
  done < <(discover_project_roots)
fi

if [[ ${#PROJECT_ROOTS[@]} -eq 0 ]]; then
  echo "No Unity projects with com.xuunity.light-mcp were discovered." >&2
  exit 1
fi

if [[ -n "$RESULTS_DIR" ]]; then
  mkdir -p "$RESULTS_DIR"
  results_dir="$(python3 - "$RESULTS_DIR" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).resolve())
PY
)"
else
  results_dir="$(mktemp -d "${TMPDIR:-/tmp}/xuunity_multi_project_batch_compile.XXXXXX")"
fi

if [[ "$KEEP_RESULTS" == "false" ]]; then
  trap 'rm -rf "$results_dir"' EXIT
fi

printf 'discovered_projects=%s\n' "${#PROJECT_ROOTS[@]}"
printf 'parallelism=%s\n' "$PARALLELISM"
printf 'close_live_editors=%s\n' "$CLOSE_LIVE_EDITORS"
printf 'batch_fallback_mode=%s\n' "$BATCH_FALLBACK_MODE"
printf 'results_dir=%s\n' "$results_dir"

printf '%s\0' "${PROJECT_ROOTS[@]}" | \
  xargs -0 -n1 -P "$PARALLELISM" "$0" __worker__ "$results_dir" "$CLOSE_LIVE_EDITORS" "$BATCH_FALLBACK_MODE"

emit_final_summary "$results_dir"
