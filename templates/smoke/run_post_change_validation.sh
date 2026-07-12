#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OPS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WRAPPER="${XUUNITY_LIGHT_UNITY_MCP_WRAPPER:-$OPS_ROOT/xuunity_light_unity_mcp.sh}"

PROJECT_ROOT=""
ACCEPTANCE_SCENARIO=""
CONTRACT_SCENARIO=""
COMPILE_MODE="build-config-matrix"
PLAYMODE_REGRESSION_ASSEMBLY_NAME=""
PLAYMODE_REGRESSION_TEST_NAME=""
RESTORE_EDITOR_STATE="true"
OPEN_EDITOR="true"
COMPILE_MATRIX_TIMEOUT_MS="300000"
ACCEPTANCE_SCENARIO_TIMEOUT_MS="180000"
CONTRACT_SCENARIO_TIMEOUT_MS="180000"
TMP_DIR=""
LAST_OUTPUT_FILE=""
SUITE_STARTED_UNIX=""
HEARTBEAT_INTERVAL_SECONDS=15
COMPILE_GATE_SOURCE=""

usage() {
  cat <<'EOF'
Usage:
  run_post_change_validation.sh \
    --project-root /path/to/UnityProject \
    --acceptance-scenario /path/to/acceptance.json \
    --contract-scenario /path/to/contract.json \
    [--compile-mode build-config-matrix|none] \
    [--compile-matrix-timeout-ms 300000] \
    [--acceptance-scenario-timeout-ms 180000] \
    [--contract-scenario-timeout-ms 180000] \
    [--playmode-regression-assembly-name PlayMode.Tests] \
    [--playmode-regression-test-name MyPlayModeTest] \
    [--no-open-editor] \
    [--no-restore-editor-state]
EOF
}

fail_usage() {
  echo "$1" >&2
  usage >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root)
      shift
      [[ $# -gt 0 ]] || fail_usage "--project-root requires a value"
      PROJECT_ROOT="$1"
      ;;
    --acceptance-scenario)
      shift
      [[ $# -gt 0 ]] || fail_usage "--acceptance-scenario requires a value"
      ACCEPTANCE_SCENARIO="$1"
      ;;
    --contract-scenario)
      shift
      [[ $# -gt 0 ]] || fail_usage "--contract-scenario requires a value"
      CONTRACT_SCENARIO="$1"
      ;;
    --compile-mode)
      shift
      [[ $# -gt 0 ]] || fail_usage "--compile-mode requires a value"
      COMPILE_MODE="$1"
      ;;
    --compile-matrix-timeout-ms)
      shift
      [[ $# -gt 0 ]] || fail_usage "--compile-matrix-timeout-ms requires a value"
      COMPILE_MATRIX_TIMEOUT_MS="$1"
      ;;
    --acceptance-scenario-timeout-ms)
      shift
      [[ $# -gt 0 ]] || fail_usage "--acceptance-scenario-timeout-ms requires a value"
      ACCEPTANCE_SCENARIO_TIMEOUT_MS="$1"
      ;;
    --contract-scenario-timeout-ms)
      shift
      [[ $# -gt 0 ]] || fail_usage "--contract-scenario-timeout-ms requires a value"
      CONTRACT_SCENARIO_TIMEOUT_MS="$1"
      ;;
    --playmode-regression-assembly-name)
      shift
      [[ $# -gt 0 ]] || fail_usage "--playmode-regression-assembly-name requires a value"
      PLAYMODE_REGRESSION_ASSEMBLY_NAME="$1"
      ;;
    --playmode-regression-test-name)
      shift
      [[ $# -gt 0 ]] || fail_usage "--playmode-regression-test-name requires a value"
      PLAYMODE_REGRESSION_TEST_NAME="$1"
      ;;
    --no-open-editor)
      OPEN_EDITOR="false"
      ;;
    --no-restore-editor-state)
      RESTORE_EDITOR_STATE="false"
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

[[ -n "$PROJECT_ROOT" ]] || fail_usage "missing required argument: --project-root"
[[ -n "$ACCEPTANCE_SCENARIO" ]] || fail_usage "missing required argument: --acceptance-scenario"
[[ -n "$CONTRACT_SCENARIO" ]] || fail_usage "missing required argument: --contract-scenario"

case "$COMPILE_MODE" in
  build-config-matrix|none)
    ;;
  *)
    fail_usage "unsupported --compile-mode value: $COMPILE_MODE"
    ;;
esac

if [[ -n "$PLAYMODE_REGRESSION_ASSEMBLY_NAME" || -n "$PLAYMODE_REGRESSION_TEST_NAME" ]]; then
  [[ -n "$PLAYMODE_REGRESSION_ASSEMBLY_NAME" ]] || fail_usage "--playmode-regression-test-name requires --playmode-regression-assembly-name"
  [[ -n "$PLAYMODE_REGRESSION_TEST_NAME" ]] || fail_usage "--playmode-regression-assembly-name requires --playmode-regression-test-name"
fi

TMP_DIR="$(mktemp -d)"

emit_phase() {
  local phase_name="$1"
  local status="$2"
  local detail="${3:-}"
  if [[ -n "$detail" ]]; then
    echo "[phase] $phase_name status=$status $detail"
  else
    echo "[phase] $phase_name status=$status"
  fi
}

emit_heartbeat() {
  local phase_name="$1"
  local detail="${2:-}"
  if [[ -n "$detail" ]]; then
    echo "[heartbeat] phase=$phase_name $detail"
  else
    echo "[heartbeat] phase=$phase_name"
  fi
}

run_restore_with_heartbeat() {
  local output_file="$TMP_DIR/cleanup_restore.json"
  local error_file="$TMP_DIR/cleanup_restore.stderr"
  local started_seconds="$SECONDS"
  local restore_pid=""

  "$WRAPPER" restore-editor-state \
    --project-root "$PROJECT_ROOT" \
    --timeout-ms 30000 >"$output_file" 2>"$error_file" &
  restore_pid="$!"

  while kill -0 "$restore_pid" >/dev/null 2>&1; do
    sleep "$HEARTBEAT_INTERVAL_SECONDS"
    if kill -0 "$restore_pid" >/dev/null 2>&1; then
      emit_heartbeat "cleanup_restore" "elapsed_seconds=$((SECONDS - started_seconds)) waiting_for=restore-editor-state"
    fi
  done

  if wait "$restore_pid"; then
    emit_phase "cleanup/restore" "passed"
  else
    local restore_rc="$?"
    emit_phase "cleanup/restore" "warn" "restore_rc=$restore_rc"
  fi
}

cleanup() {
  if [[ "$RESTORE_EDITOR_STATE" == "true" ]]; then
    emit_phase "cleanup/restore" "running"
    run_restore_with_heartbeat || true
  else
    emit_phase "cleanup/restore" "skipped"
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

fail_step() {
  local step_name="$1"
  echo "[fail] $step_name"
  if [[ -n "$LAST_OUTPUT_FILE" && -f "$LAST_OUTPUT_FILE" ]]; then
    echo "[fail] output follows:"
    cat "$LAST_OUTPUT_FILE"
  fi
  exit 1
}

run_step() {
  local step_name="$1"
  shift
  LAST_OUTPUT_FILE="$TMP_DIR/${step_name}.json"
  if ! "$@" > "$LAST_OUTPUT_FILE"; then
    fail_step "$step_name"
  fi
}

summarize_json() {
  local label="$1"
  local file_path="$2"
  local python_code="$3"

  if ! python3 - "$label" "$file_path" "$python_code" <<'PY'; then
import json
import sys
from pathlib import Path

label = sys.argv[1]
file_path = Path(sys.argv[2])
python_code = sys.argv[3]

data = json.loads(file_path.read_text())
namespace = {"data": data}
summary = eval(python_code, {}, namespace)
print(f"[pass] {label} {summary}".rstrip())
PY
    fail_step "$label"
  fi
}

print_lifecycle_summary() {
  local initial_file="$1"
  local final_file="$2"
  local verdict="$3"

  python3 - "$initial_file" "$final_file" "$SUITE_STARTED_UNIX" "$PROJECT_ROOT" "$verdict" <<'PY'
import json
import sys
from pathlib import Path

initial_file = Path(sys.argv[1])
final_file = Path(sys.argv[2])
started_unix = float(sys.argv[3])
project_root = Path(sys.argv[4])
verdict = sys.argv[5]


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


initial = read_json(initial_file)
final = read_json(final_file)
initial_bridge = initial.get("bridge_state") or {}
journal_dir = project_root / "Library" / "XUUnityLightMcp" / "journal" / "requests"

event_counts = {
    "request_abandoned": 0,
    "request_reclassified": 0,
    "bridge_bootstrap_attached": 0,
    "request_completed": 0,
}
abandoned_request_ids = set()
recovered_request_ids = set()

if journal_dir.is_dir():
    for event_path in journal_dir.glob("*.json"):
        try:
            if event_path.stat().st_mtime < started_unix:
                continue
            event = read_json(event_path)
        except OSError:
            continue

        event_type = str(event.get("event_type") or "")
        if event_type in event_counts:
            event_counts[event_type] += 1

        request_id = str(event.get("request_id") or "")
        if event_type == "request_abandoned" and request_id:
            abandoned_request_ids.add(request_id)
        elif event_type in {"request_completed", "request_reclassified"} and request_id:
            recovered_request_ids.add(request_id)

initial_generation = int(initial_bridge.get("bridge_generation") or 0)
final_generation = int(final.get("bridge_generation") or 0)
generation_delta = final_generation - initial_generation if initial_generation and final_generation else 0
stale_request_count = int(((final.get("stale_request_artifacts") or {}).get("candidate_count")) or 0)
unrecovered_abandoned = sorted(abandoned_request_ids - recovered_request_ids)
final_health = str(final.get("health_status") or "")
final_playmode = str(final.get("playmode_state") or "")
compiler_errors = int(final.get("compiler_error_count") or 0)
terminal_passed = verdict == "passed"

churn_classification = "none"
if generation_delta > 5:
    churn_classification = (
        "non_blocking_churn"
        if (
            terminal_passed
            and final_health == "healthy"
            and compiler_errors == 0
            and not unrecovered_abandoned
        )
        else "actionable_churn"
    )

warning_codes = []
if churn_classification == "actionable_churn":
    warning_codes.append("actionable_churn")
if unrecovered_abandoned:
    warning_codes.append("unrecovered_request_abandoned")
if final_health != "healthy":
    warning_codes.append("final_health_not_healthy")
if final_playmode != "edit":
    warning_codes.append("final_playmode_not_edit")
if compiler_errors != 0:
    warning_codes.append("compiler_errors_present")
if stale_request_count != 0:
    warning_codes.append("stale_requests_present")

label = "warn" if warning_codes else "pass"
print(
    f"[{label}] lifecycle-churn "
    f"initial_generation={initial_generation} "
    f"final_generation={final_generation} "
    f"generation_delta={generation_delta} "
    f"initial_session={initial_bridge.get('bridge_session_id') or '-'} "
    f"final_session={final.get('bridge_session_id') or '-'} "
    f"bridge_bootstraps={event_counts['bridge_bootstrap_attached']} "
    f"reclassified={event_counts['request_reclassified']} "
    f"abandoned={event_counts['request_abandoned']} "
    f"unrecovered_abandoned={len(unrecovered_abandoned)} "
    f"terminal_verdict={verdict} "
    f"final_health={final_health or '-'} "
    f"final_playmode={final_playmode or '-'} "
    f"compiler_errors={compiler_errors} "
    f"stale_requests={stale_request_count} "
    f"churn_classification={churn_classification} "
    f"warning_codes={','.join(warning_codes) if warning_codes else 'none'}"
)
PY
}

maybe_reuse_healthy_editor() {
  local status_summary_file="$TMP_DIR/status_summary_preflight.json"
  local status_summary_error_file="$TMP_DIR/status_summary_preflight.stderr"
  local bridge_state_file="$TMP_DIR/bridge_state_preflight.json"
  local bridge_state_error_file="$TMP_DIR/bridge_state_preflight.stderr"
  local lane_probe=""
  local lane_probe_kind="unknown"
  local lane_probe_pid="0"
  local lane_probe_source="none"

  echo "[lane] lane_decision=probing reason=checking_existing_editor"

  if "$WRAPPER" request-status-summary \
    --project-root "$PROJECT_ROOT" \
    --timeout-ms 5000 >"$status_summary_file" 2>"$status_summary_error_file"; then
    if lane_probe="$(python3 - "$status_summary_file" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
editor_running = bool(data.get("editor_running"))
visibility_proven = (
    data.get("process_visibility_available") is not False and
    not bool(data.get("process_visibility_restricted"))
)
ready = (
    editor_running and
    bool(data.get("mcp_reachable")) and
    data.get("health_status") == "healthy" and
    int(data.get("pending_request_count") or 0) == 0 and
    data.get("playmode_state") == "edit"
)
kind = (
    "healthy"
    if ready
    else ("live" if editor_running else ("closed" if visibility_proven else "unknown"))
)
print(f"{kind}:{int(data.get('editor_pid') or 0)}")
PY
)"; then
      lane_probe_kind="${lane_probe%%:*}"
      lane_probe_pid="${lane_probe#*:}"
      lane_probe_source="request-status-summary"
    else
      echo "[warn] request-status-summary returned invalid JSON; checking direct bridge state" >&2
    fi
  else
    echo "[warn] request-status-summary preflight failed; checking direct bridge state" >&2
    while IFS= read -r line; do
      echo "[preflight-stderr] $line" >&2
    done <"$status_summary_error_file"
  fi

  if [[ "$lane_probe_kind" != "healthy" && "$lane_probe_kind" != "live" ]]; then
    if "$WRAPPER" bridge-state \
      --project-root "$PROJECT_ROOT" >"$bridge_state_file" 2>"$bridge_state_error_file"; then
      if lane_probe="$(python3 - "$bridge_state_file" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
live = bool((data.get("_xuunity_bridge_state") or {}).get("state_is_live"))
ready = (
    live and
    data.get("health_status") == "healthy" and
    int(data.get("pending_request_count") or 0) == 0 and
    data.get("playmode_state") == "edit"
)
kind = "healthy" if ready else ("live" if live else "unknown")
print(f"{kind}:{int(data.get('editor_pid') or 0)}")
PY
)"; then
        if [[ "${lane_probe%%:*}" == "healthy" || "${lane_probe%%:*}" == "live" ]]; then
          lane_probe_kind="${lane_probe%%:*}"
          lane_probe_pid="${lane_probe#*:}"
          lane_probe_source="bridge-state"
        fi
      else
        echo "[warn] bridge-state preflight returned invalid JSON" >&2
      fi
    else
      echo "[warn] bridge-state preflight failed" >&2
      while IFS= read -r line; do
        echo "[preflight-stderr] $line" >&2
      done <"$bridge_state_error_file"
    fi
  fi

  if [[ "$lane_probe_kind" == "healthy" ]]; then
    OPEN_EDITOR="false"
    echo "[lane] lane_decision=interactive_mcp reason=healthy_existing_editor source=$lane_probe_source pid=$lane_probe_pid"
    return 0
  fi

  if [[ "$lane_probe_kind" == "live" ]]; then
    OPEN_EDITOR="false"
    echo "[lane] lane_decision=interactive_mcp reason=live_editor_requires_interactive_recovery source=$lane_probe_source pid=$lane_probe_pid"
    return 0
  fi

  if [[ "$lane_probe_kind" == "closed" ]]; then
    echo "[lane] lane_decision=closed_batch_preflight reason=status_summary_confirmed_no_editor"
    return 0
  fi

  echo "[lane] lane_decision=blocked reason=editor_liveness_unproven"
  echo "[error] Cannot safely choose batch or interactive validation because editor liveness is unproven. Run request-status-summary and bridge-state, then retry." >&2
  return 1
}

echo "[mcp-validate] project_root=$PROJECT_ROOT"
SUITE_STARTED_UNIX="$(python3 - <<'PY'
import time
print(f"{time.time():.6f}")
PY
)"

if [[ "$OPEN_EDITOR" == "true" ]]; then
  maybe_reuse_healthy_editor
fi

if [[ "$COMPILE_MODE" == "build-config-matrix" && "$OPEN_EDITOR" == "true" ]]; then
  emit_phase "compile preflight" "running" "mode=batch-build-config-compile-matrix"
  run_step compile_preflight \
    "$WRAPPER" batch-build-config-compile-matrix \
    --project-root "$PROJECT_ROOT" \
    --timeout-ms "$COMPILE_MATRIX_TIMEOUT_MS" \
    --batch-fallback-mode require-batch \
    --output compact \
    --no-progress-stdout
  summarize_json \
    "compile-preflight" \
    "$TMP_DIR/compile_preflight.json" \
    "\"lane=%s status=%s passed=%s/%s next=%s\" % (data.get('effective_execution_lane') or data.get('requested_execution_lane') or '-', (data.get('matrix') or {}).get('status') or ('passed' if data.get('succeeded') else 'failed'), (data.get('matrix') or {}).get('passed', 0), (data.get('matrix') or {}).get('total', 0), data.get('recommended_next_action') or 'none')"
  COMPILE_GATE_SOURCE="batch_preflight"
  emit_phase "compile preflight" "passed" "source=batch-build-config-compile-matrix"
else
  emit_phase "compile preflight" "skipped" "reason=healthy-or-managed-editor compile_mode=$COMPILE_MODE"
fi

emit_phase "readiness" "running"
ensure_ready_cmd=(
  "$WRAPPER" ensure-ready
  --project-root "$PROJECT_ROOT"
  --timeout-ms 180000
)
if [[ "$OPEN_EDITOR" == "true" ]]; then
  ensure_ready_cmd+=(--open-editor)
fi

run_step ensure_ready "${ensure_ready_cmd[@]}"
summarize_json \
  "ensure-ready" \
  "$TMP_DIR/ensure_ready.json" \
  "\"bridge=%s health=%s playmode=%s\" % (data['bridge_state'].get('bridge_version'), data['bridge_state'].get('health_status'), data['bridge_state'].get('playmode_state'))"

run_step status \
  "$WRAPPER" request-status \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 15000
summarize_json \
  "status" \
  "$TMP_DIR/status.json" \
  "\"health=%s playmode=%s last_completed=%s/%s\" % ((lambda payload: (payload.get('health_status'), payload.get('playmode_state'), payload.get('last_completed_operation'), payload.get('last_completed_operation_status')))(__import__('json').loads(data['payload_json'])))"

run_step health_probe \
  "$WRAPPER" request-health-probe \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 15000
summarize_json \
  "health-probe" \
  "$TMP_DIR/health_probe.json" \
  "\"status=%s supported_ops=%s\" % ((lambda report: (report.get('status'), len(report.get('supported_operations') or [])))(__import__('json').loads(data['payload_json']).get('report') or {}))"
emit_phase "readiness" "passed"

if [[ "$COMPILE_MODE" == "build-config-matrix" ]]; then
  if [[ "$COMPILE_GATE_SOURCE" == "batch_preflight" ]]; then
    emit_phase "compile matrix" "passed" "source=batch-preflight"
    echo "[pass] compile-matrix source=batch-preflight"
  else
    emit_phase "compile matrix" "running"
    run_step compile_matrix \
      "$WRAPPER" request-build-config-compile-matrix \
      --project-root "$PROJECT_ROOT" \
      --timeout-ms "$COMPILE_MATRIX_TIMEOUT_MS"
    summarize_json \
      "compile-matrix" \
      "$TMP_DIR/compile_matrix.json" \
      "\"status=%s passed=%s/%s basis=%s duration=%.3fs\" % ((lambda matrix: (matrix.get('status'), matrix.get('passed'), matrix.get('total'), matrix.get('completion_basis'), float(matrix.get('duration_seconds') or 0.0)))(__import__('json').loads(data['bridge_response']['payload_json'])))"
    emit_phase "compile matrix" "passed" "source=bridge"
  fi
else
  emit_phase "compile matrix" "skipped" "compile_mode=none"
  echo "[skip] compile-matrix compile_mode=none"
fi

emit_phase "acceptance scenario" "running"
run_step acceptance_scenario \
  "$WRAPPER" request-scenario-run-and-wait \
  --project-root "$PROJECT_ROOT" \
  --scenario-file "$ACCEPTANCE_SCENARIO" \
  --timeout-ms "$ACCEPTANCE_SCENARIO_TIMEOUT_MS" \
  --poll-interval-ms 500 \
  --include-full-payload
summarize_json \
  "acceptance-scenario" \
  "$TMP_DIR/acceptance_scenario.json" \
  "\"status=%s steps=%s/%s duration=%.3fs\" % ((lambda payload, steps: (payload.get('status') or payload.get('terminal_status') or ((payload.get('run_start') or {}).get('status')), payload.get('passed_steps') if payload.get('passed_steps') is not None else sum(1 for step in steps if step.get('status') == 'passed'), payload.get('total_steps') if payload.get('total_steps') is not None else len(steps), float(payload.get('duration_seconds') or 0.0)))(data, (data.get('steps') or ((data.get('run_start') or {}).get('steps')) or [])))"
emit_phase "acceptance scenario" "passed"

emit_phase "contract scenario" "running"
run_step contract_scenario \
  "$WRAPPER" request-scenario-run-and-wait \
  --project-root "$PROJECT_ROOT" \
  --scenario-file "$CONTRACT_SCENARIO" \
  --timeout-ms "$CONTRACT_SCENARIO_TIMEOUT_MS" \
  --poll-interval-ms 500 \
  --include-full-payload
summarize_json \
  "contract-scenario" \
  "$TMP_DIR/contract_scenario.json" \
  "\"status=%s refresh=%s compile=%s duration=%.3fs\" % ((data.get('status') or data.get('terminal_status') or ((data.get('run_start') or {}).get('status'))), next((__import__('json').loads(step.get('payload_json') or '{}').get('outcome') for step in ((data.get('steps') or ((data.get('run_start') or {}).get('steps')) or [])) if step.get('stepId') == 'refresh'), 'unknown'), next((__import__('json').loads(step.get('payload_json') or '{}').get('completion_basis') for step in ((data.get('steps') or ((data.get('run_start') or {}).get('steps')) or [])) if step.get('stepId') == 'compile'), 'unknown'), float(data.get('duration_seconds') or 0.0))"
emit_phase "contract scenario" "passed"

if [[ -n "$PLAYMODE_REGRESSION_ASSEMBLY_NAME" ]]; then
  emit_phase "PlayMode/lifecycle checks" "running"
  run_step playmode_settled_state_regression \
    "$SCRIPT_DIR/run_playmode_settled_state_regression.sh" \
    --project-root "$PROJECT_ROOT" \
    --assembly-name "$PLAYMODE_REGRESSION_ASSEMBLY_NAME" \
    --test-name "$PLAYMODE_REGRESSION_TEST_NAME" \
    --no-open-editor \
    --no-restore-editor-state
  echo "[pass] playmode-settled-state-regression"

  run_step playmode_lifecycle_retry_smoke \
    "$SCRIPT_DIR/run_playmode_lifecycle_retry_smoke.sh" \
    --project-root "$PROJECT_ROOT" \
    --assembly-name "$PLAYMODE_REGRESSION_ASSEMBLY_NAME" \
    --test-name "$PLAYMODE_REGRESSION_TEST_NAME" \
    --no-open-editor \
    --no-restore-editor-state
  echo "[pass] playmode-lifecycle-retry-smoke"
  emit_phase "PlayMode/lifecycle checks" "passed"
else
  emit_phase "PlayMode/lifecycle checks" "skipped" "playmode_regression_args=absent"
fi

emit_phase "main proof" "passed" "auxiliary_checks=running"
emit_phase "auxiliary consistency checks" "running"
emit_heartbeat "auxiliary_consistency_checks" "waiting_for=request-status-summary"
run_step final_status \
  "$WRAPPER" request-status-summary \
  --project-root "$PROJECT_ROOT" \
  --timeout-ms 15000
print_lifecycle_summary "$TMP_DIR/ensure_ready.json" "$TMP_DIR/final_status.json" "passed"
emit_phase "auxiliary consistency checks" "passed"

emit_phase "suite" "passed"
echo "[pass] suite overall"
