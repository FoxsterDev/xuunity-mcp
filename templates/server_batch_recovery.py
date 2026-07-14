# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from server_batch_context import (
    RECOVERY_RECONCILIATION_ACTIONS,
    build_status_summary_from_context,
    current_project_context_bridge_state,
    current_project_context_discovery_details,
    enrich_error_details_with_discovery,
    enrich_tool_invocation_error_with_discovery,
    recommended_recovery_command_for_project,
)
from server_bridge_runtime import (
    DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
    bridge_state_path,
    default_editor_log_path,
    try_read_live_editor_state,
)
from server_core import ToolInvocationError
from server_editor_host import (
    activate_unity_editor,
    bridge_state_is_ready,
    default_batch_operation_log_path,
    detect_unity_app_path_for_project,
    find_running_unity_editors_for_project,
    open_unity_editor,
    process_visibility_summary,
    terminate_editor_pid,
    update_host_editor_session_pid,
    wait_for_ready,
)
from server_project_reporting import build_discovery_status_summary_for_error_data
from server_registry import refresh_project_context
from server_summaries import truncate_text
from server_process_launcher import ProcessLauncher

def build_batch_editor_conflict_details(project_root: Path, live_editor_pids: list[int]) -> dict[str, Any]:
    next_action = "close_same_project_editor_or_use_interactive_lane"
    visibility = process_visibility_summary()
    return {
        "live_editor_pids": live_editor_pids,
        "live_project_editor_pids": live_editor_pids,
        "same_project_editor_closed": False,
        "process_exit_verified": False,
        "process_visibility_available": bool(visibility.get("process_visibility_available")),
        "process_visibility_error_code": str(visibility.get("process_visibility_error_code") or ""),
        "closeout_classification": "editor_still_running",
        "recommended_next_action": next_action,
        "next_distinct_action": "request_quit_wait_for_exit_then_verify_closed",
        "recommended_recovery_command": recommended_recovery_command_for_project(project_root, next_action),
        "closeout_verification_required": True,
        "closeout_verification_note": "Verify editor process exit before rerunning the closed-project batch lane.",
    }


def _best_effort_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def build_editor_relaunch_attribution(
    *,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
    previous_editor_pid: int,
    current_editor_pid: int,
    cold_start_reason: str,
) -> dict[str, Any]:
    before = before_state if isinstance(before_state, dict) else {}
    after = after_state if isinstance(after_state, dict) else {}
    return {
        "editor_relaunched": True,
        "previous_editor_pid": _best_effort_int(previous_editor_pid or before.get("editor_pid")),
        "current_editor_pid": _best_effort_int(current_editor_pid or after.get("editor_pid")),
        "bridge_generation_before": _best_effort_int(before.get("bridge_generation")),
        "bridge_generation_after": _best_effort_int(after.get("bridge_generation")),
        "cold_start_reason": cold_start_reason,
    }


def execute_host_health_recovery_policy(
    project_root: Path,
    *,
    timeout_ms: int,
    startup_policy: str,
    allow_open_editor: bool,
    background_open: bool = False,
    allow_force_terminate: bool = False,
) -> dict[str, Any]:
    before_state = current_project_context_bridge_state(project_root)
    discovery = current_project_context_discovery_details(project_root)
    termination_policy = str(discovery.get("host_health_termination_policy") or "observe_only")
    health_classification = str(discovery.get("host_health_classification") or "")
    result: dict[str, Any] = {
        "host_health_classification": health_classification,
        "termination_policy": termination_policy,
        "force_termination_authorized": bool(allow_force_terminate),
        "action": "none",
    }

    if health_classification not in {"anr", "anr_suspected"}:
        return result

    if termination_policy == "observe_only":
        result["action"] = "observe_only"
        return result

    if not allow_open_editor:
        result["action"] = "termination_deferred_no_open"
        return result

    if not allow_force_terminate:
        result["action"] = "termination_deferred_force_not_authorized"
        result["recommended_next_action"] = "manual_editor_close_or_explicit_force_terminate"
        return result

    detected_pids = {
        int(value or 0)
        for value in (discovery.get("detected_editor_pids") or [])
        if int(value or 0) > 0
    }
    candidate_pid = 0
    for value in (
        int(discovery.get("bridge_pid") or 0),
        int(discovery.get("host_session_pid") or 0),
    ):
        if value > 0 and value in detected_pids:
            candidate_pid = value
            break
    if candidate_pid <= 0:
        candidate_pid = min(detected_pids) if detected_pids else 0

    if candidate_pid <= 0:
        result["action"] = "no_live_pid_for_termination"
        return result

    result["target_editor_pid"] = candidate_pid

    visibility = process_visibility_summary()
    verified_editor_pids = {
        int(editor.get("pid") or 0)
        for editor in find_running_unity_editors_for_project(project_root)
        if int(editor.get("pid") or 0) > 0
    }
    if (
        not bool(visibility.get("process_visibility_available"))
        or candidate_pid not in verified_editor_pids
    ):
        result["action"] = "termination_skipped_identity_unverified"
        result["process_visibility_available"] = bool(visibility.get("process_visibility_available"))
        result["process_visibility_error_code"] = str(visibility.get("process_visibility_error_code") or "")
        result["verified_project_editor_pids"] = sorted(verified_editor_pids)
        return result

    result["terminated"] = terminate_editor_pid(candidate_pid, min(timeout_ms, 15000))
    if not bool(result.get("terminated")):
        result["action"] = "termination_failed"
        return result

    result["action"] = "terminated_editor"
    refresh_project_context(project_root)

    if not allow_open_editor:
        return result

    unity_app = detect_unity_app_path_for_project(project_root, None)
    log_path = default_editor_log_path(project_root)
    launch = open_unity_editor(project_root, log_path, unity_app, background_open)
    state = wait_for_ready(
        project_root=project_root,
        timeout_ms=timeout_ms,
        heartbeat_max_age_seconds=DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
        startup_policy=startup_policy,
        editor_log_path=log_path,
    )
    result["launch"] = launch
    result["bridge_state"] = state
    result.update(
        build_editor_relaunch_attribution(
            before_state=before_state,
            after_state=state,
            previous_editor_pid=candidate_pid,
            current_editor_pid=int(state.get("editor_pid") or launch.get("editor_pid") or 0),
            cold_start_reason=f"host_health_{health_classification or 'recovery'}",
        )
    )
    if not bool((launch or {}).get("reused_existing_editor")):
        update_host_editor_session_pid(project_root, int(state.get("editor_pid") or 0))
    refresh_project_context(project_root)
    result["action"] = "terminated_and_reopened"
    return result


def recover_project_bridge_for_reconciliation(
    project_root: Path,
    *,
    timeout_ms: int,
    heartbeat_max_age_seconds: int,
    startup_policy: str,
    allow_open_editor: bool,
    background_open: bool = False,
    allow_force_terminate: bool = False,
) -> dict[str, Any]:
    current_state = current_project_context_bridge_state(project_root)
    discovery = current_project_context_discovery_details(project_root)
    next_action = str(discovery.get("reconciliation_recommended_next_action") or "")

    recovery: dict[str, Any] = {
        "reconciliation_case": str(discovery.get("reconciliation_case") or ""),
        "reconciliation_status": str(discovery.get("reconciliation_status") or ""),
        "reconciliation_recommended_next_action": next_action,
        "allow_open_editor": allow_open_editor,
        "allow_force_terminate": bool(allow_force_terminate),
        "action": "none",
    }

    if bridge_state_is_ready(current_state, heartbeat_max_age_seconds):
        recovery["action"] = "already_ready"
        return recovery

    host_health_recovery = execute_host_health_recovery_policy(
        project_root,
        timeout_ms=timeout_ms,
        startup_policy=startup_policy,
        allow_open_editor=allow_open_editor,
        background_open=background_open,
        allow_force_terminate=allow_force_terminate,
    )
    recovery["host_health_recovery"] = host_health_recovery
    if str(host_health_recovery.get("action") or "") in {
        "terminated_editor",
        "terminated_and_reopened",
        "termination_failed",
        "no_live_pid_for_termination",
        "termination_deferred_no_open",
        "termination_deferred_force_not_authorized",
        "termination_skipped_identity_unverified",
    }:
        recovery["action"] = str(host_health_recovery.get("action") or "none")
        return recovery

    if next_action == "enable_bridge_and_retry":
        raise enrich_tool_invocation_error_with_discovery(
            project_root,
            ToolInvocationError(
                "bridge_disabled",
                (
                    "Unity bridge is disabled for this project. "
                    "Enable it with init_xuunity_light_unity_mcp.sh --project-root <path> --enable-project "
                    "and reopen Unity."
                ),
            ),
        )

    if next_action == "refresh_host_session_if_needed":
        refresh_project_context(project_root)
        recovery["action"] = "refreshed_context"
        return recovery

    if next_action not in RECOVERY_RECONCILIATION_ACTIONS:
        return recovery

    detected_editor_count = int(discovery.get("detected_editor_count") or 0)
    log_path = default_editor_log_path(project_root)
    if detected_editor_count > 0:
        recovery["activation"] = activate_unity_editor(project_root)
        recovery["action"] = "activated_existing_editor"
    elif allow_open_editor:
        unity_app = detect_unity_app_path_for_project(project_root, None)
        launch = open_unity_editor(project_root, log_path, unity_app, background_open)
        recovery["launch"] = launch
        recovery["action"] = "opened_editor"
    else:
        recovery["action"] = "recovery_deferred_no_open"
        return recovery

    state = wait_for_ready(
        project_root=project_root,
        timeout_ms=timeout_ms,
        heartbeat_max_age_seconds=heartbeat_max_age_seconds,
        startup_policy=startup_policy,
        editor_log_path=log_path,
    )
    recovery["bridge_state"] = state
    launch_payload = recovery.get("launch")
    if isinstance(launch_payload, dict) and not bool(launch_payload.get("reused_existing_editor")):
        recovery.update(
            build_editor_relaunch_attribution(
                before_state=current_state,
                after_state=state,
                previous_editor_pid=int(current_state.get("editor_pid") or 0),
                current_editor_pid=int(state.get("editor_pid") or launch_payload.get("editor_pid") or 0),
                cold_start_reason=str(discovery.get("reconciliation_case") or next_action or "open_editor_recovery"),
            )
        )
        update_host_editor_session_pid(project_root, int(state.get("editor_pid") or 0))
    refresh_project_context(project_root)
    return recovery


def maybe_fail_fast_offline_ensure_ready_without_open(
    project_root: Path,
    discovery: dict[str, Any],
) -> None:
    if str(discovery.get("reconciliation_case") or "") != "host_launchable_not_active":
        return

    next_action = str(discovery.get("reconciliation_recommended_next_action") or "open_editor_or_ensure_ready")
    recovery_command = recommended_recovery_command_for_project(project_root, next_action)
    details = dict(discovery)
    details.update({
        "fail_fast_reason": "ensure_ready_without_open_editor_offline",
        "recommended_next_action": next_action,
        "recommended_recovery_command": recovery_command,
    })
    message = (
        "No matching Unity editor is running for this project, so plain ensure-ready cannot observe a bridge. "
        "Run ensure-ready with --open-editor to start the project editor."
    )
    if recovery_command:
        message += f" next_step: {recovery_command}"
    raise ToolInvocationError("editor_not_running", message, details)


def build_discovery_status_summary_for_error(
    project_root: Path,
    exc: ToolInvocationError | None = None,
) -> dict[str, Any]:
    return build_discovery_status_summary_for_error_data(
        project_root,
        exc=exc,
        discovery=current_project_context_discovery_details(project_root),
        build_status_summary_from_context=build_status_summary_from_context,
        enrich_error_details_with_discovery=enrich_error_details_with_discovery,
    )


def run_batch_build_config_compile_matrix_probe(
    project_root: Path,
    *,
    timeout_ms: int,
) -> dict[str, Any]:
    command = [
        *(ProcessLauncher.get_self_invocation_base_command()),
        "batch-build-config-compile-matrix",
        "--project-root",
        str(project_root),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    stdout = str(completed.stdout or "").strip()
    stderr = str(completed.stderr or "").strip()
    payload: dict[str, Any] = {
        "action": "batch_build_config_compile_matrix_probe",
        "command": command,
        "batch_exit_code": completed.returncode,
        "timeout_ms": timeout_ms,
    }

    if stdout:
        try:
            payload["batch_probe"] = json.loads(stdout)
        except json.JSONDecodeError:
            payload["batch_probe_stdout"] = truncate_text(stdout, 1200)
    if stderr:
        payload["batch_probe_stderr"] = truncate_text(stderr, 1200)

    batch_probe = payload.get("batch_probe")
    if isinstance(batch_probe, dict):
        payload["succeeded"] = bool(batch_probe.get("succeeded"))
        payload["summary_file"] = str(batch_probe.get("summary_file") or "")
        payload["result_file"] = str(batch_probe.get("result_file") or "")
        payload["log_path"] = str(batch_probe.get("log_path") or "")
        result_summary = batch_probe.get("result_summary")
        if isinstance(result_summary, dict):
            payload["compile_gate_summary"] = result_summary
            payload["top_actionable_error"] = str(result_summary.get("top_actionable_error") or "")
    else:
        payload["succeeded"] = completed.returncode == 0

    return payload


def classify_compile_probe_failure(compile_probe: dict[str, Any]) -> tuple[str, str, str]:
    batch_probe = dict(compile_probe.get("batch_probe") or {})
    error_payload = dict(batch_probe.get("error") or {})
    error_code = str(error_payload.get("code") or "")

    if error_code == "editor_running_batch_conflict":
        return (
            "compile_probe_blocked_by_live_editor",
            "close_same_project_editor_or_use_interactive_lane",
            "{launcher} request-editor-quit --project-root {project_root} --timeout-ms 30000 --wait-for-exit --exit-timeout-ms 30000",
        )

    return (
        "compile_red_confirmed",
        "fix_compile_errors_before_gui_reopen",
        "{launcher} project-discovery-report --project-root {project_root}",
    )


def run_self_json_command_with_completed(args: list[str]) -> tuple[dict[str, Any] | None, subprocess.CompletedProcess[str]]:
    completed = subprocess.run(
        ProcessLauncher.get_self_invocation_base_command() + [ *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    payload: dict[str, Any] | None = None
    stdout = str(completed.stdout or "").strip()
    if stdout:
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = None
    return payload, completed


def run_self_json_command(command_args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        ProcessLauncher.get_self_invocation_base_command() + [*command_args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout_text = completed.stdout or ""
    stderr_text = completed.stderr or ""
    parsed_stdout: dict[str, Any] | None = None
    parse_error = ""
    if stdout_text.strip():
        try:
            parsed_candidate = json.loads(stdout_text)
            if isinstance(parsed_candidate, dict):
                parsed_stdout = parsed_candidate
        except json.JSONDecodeError as exc:
            parse_error = str(exc)

    payload: dict[str, Any] = {
        "command": ProcessLauncher.get_self_invocation_base_command() + [*command_args],
        "exit_code": completed.returncode,
        "stdout": stdout_text,
        "stderr": stderr_text,
    }
    if parsed_stdout is not None:
        payload["stdout_json"] = parsed_stdout
    if parse_error:
        payload["stdout_parse_error"] = parse_error
    return payload
