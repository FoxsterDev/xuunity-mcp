# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable, TypeVar

from server_batch_reporting import first_non_empty_line
from server_bridge_runtime import (
    derive_busy_reason,
    heartbeat_age_seconds,
    pid_is_alive,
    read_best_effort_bridge_state,
    summarize_state_for_error,
)
from server_core import ToolInvocationError, read_json
from server_project_reporting import (
    apply_discovery_to_final_status_summary_data,
    apply_discovery_to_scenario_payload_data,
    build_discovery_scenario_result_summary_for_error_data,
    build_project_discovery_report_data,
    build_registry_context_report_data,
    build_request_final_status_from_context_data,
    build_scenario_result_summary_from_context_data,
    enrich_error_details_with_discovery_data,
)
from server_registry import (
    ProjectContext,
    forget_project_context,
    get_project_context,
    list_active_project_contexts,
    prune_stale_project_contexts,
    refresh_project_context,
)
from server_specs import SCENARIO_TERMINAL_STATUSES
from server_summaries import build_scenario_result_summary, build_status_summary, truncate_text

MUTATING_BRIDGE_OPERATIONS = frozenset(
    {
        "unity.project.refresh",
        "unity.compile.player_scripts",
        "unity.compile.matrix",
        "unity.tests.run_editmode",
        "unity.tests.run_playmode",
        "unity.package.install_test_framework",
        "unity.build_player",
        "unity.playmode.set",
        "unity.scene.open",
        "unity.build_target.switch",
        "unity.editor.quit",
    }
)
TProjectOperationResult = TypeVar("TProjectOperationResult")

def default_local_package_source() -> Path:
    templates_dir = Path(__file__).resolve().parent
    return templates_dir.parent / "packages" / "com.xuunity.light-mcp"


def default_light_mcp_package_version() -> str:
    package_path = default_local_package_source() / "package.json"
    try:
        payload = read_json(package_path)
    except Exception:
        return "0.0.0"
    if isinstance(payload, dict):
        return str(payload.get("version") or "0.0.0")
    return "0.0.0"


def mcp_json_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=True)}],
        "structuredContent": payload,
        "isError": is_error,
    }


def apply_discovery_to_final_status_summary(
    summary: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    return apply_discovery_to_final_status_summary_data(
        summary,
        discovery=current_project_context_discovery_details(project_root),
    )


def apply_discovery_to_scenario_payload(
    payload: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    return apply_discovery_to_scenario_payload_data(
        payload,
        project_root=project_root,
        discovery=current_project_context_discovery_details(project_root),
    )


def build_scenario_result_summary_from_context(
    project_root: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return build_scenario_result_summary_from_context_data(
        project_root,
        payload,
        discovery=current_project_context_discovery_details(project_root),
        build_scenario_result_summary=build_scenario_result_summary,
        scenario_terminal_statuses=SCENARIO_TERMINAL_STATUSES,
    )


def build_discovery_scenario_result_summary_for_error(
    project_root: Path,
    run_id: str,
    scenario_name: str,
    exc: ToolInvocationError,
) -> dict[str, Any]:
    return build_discovery_scenario_result_summary_for_error_data(
        project_root,
        run_id,
        scenario_name,
        exc,
        build_scenario_result_summary_from_context=build_scenario_result_summary_from_context,
        enrich_error_details_with_discovery=enrich_error_details_with_discovery,
    )


def build_request_final_status_from_context(
    project_root: Path,
    request_id: str,
    operation: str = "",
    poll_timeout_ms: int = 0,
) -> dict[str, Any]:
    return build_request_final_status_from_context_data(
        project_root,
        request_id,
        operation=operation,
        poll_timeout_ms=poll_timeout_ms,
        build_request_final_status=build_request_final_status,
        current_project_context_bridge_state=current_project_context_bridge_state,
        discovery=current_project_context_discovery_details(project_root),
    )


def build_tool_error_payload(exc: ToolInvocationError) -> dict[str, Any]:
    details = dict(exc.details or {})
    error: dict[str, Any] = {
        "code": exc.code,
        "message": exc.message,
    }
    if details:
        error["details"] = details

    payload: dict[str, Any] = {"error": error}
    for key in (
        "request_id",
        "request_submitted",
        "request_ownership_acquired",
        "transport_outcome",
        "operation_outcome",
        "recommended_next_action",
        "next_distinct_action",
        "closeout_classification",
        "closeout_verified",
        "process_visibility_available",
        "process_visibility_error_code",
        "same_project_editor_closed",
        "process_exit_verified",
        "quit_request_accepted",
        "requested_execution_lane",
        "effective_execution_lane",
        "lane_fallback_reason",
        "batch_fallback_mode",
        "license_batchmode_supported",
        "license_blocker_code",
        "batchmode_probe_log_path",
        "transport",
        "initial_bridge_generation",
        "initial_bridge_session_id",
        "current_bridge_generation",
        "current_bridge_session_id",
        "retryable",
        "request_processed",
        "bridge_stabilization",
        "request_final_status",
        "journal_event_path",
        "recommended_recovery_command",
        "package_import_state",
        "package_import_diagnosis",
        "live_project_editor_pids",
        "batch_summary_file",
        "batch_failure_summary",
    ):
        if key in details:
            payload[key] = details[key]
    return payload


def emit_tool_error_summary(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        return

    error = payload.get("error")
    if not isinstance(error, dict):
        return

    code = str(error.get("code") or "")
    message = first_non_empty_line(str(error.get("message") or ""), limit=200, truncate_text=truncate_text)
    request_id = str(payload.get("request_id") or "")
    request_submitted = payload.get("request_submitted")
    request_ownership_acquired = payload.get("request_ownership_acquired")
    recommended_next_action = str(payload.get("recommended_next_action") or "")
    recommended_recovery_command = str(payload.get("recommended_recovery_command") or "")
    transport_outcome = str(payload.get("transport_outcome") or "")
    operation_outcome = str(payload.get("operation_outcome") or "")
    closeout_classification = str(payload.get("closeout_classification") or "")
    closeout_verified = payload.get("closeout_verified")
    process_visibility_error_code = str(payload.get("process_visibility_error_code") or "")
    same_project_editor_closed = payload.get("same_project_editor_closed")
    process_exit_verified = payload.get("process_exit_verified")
    next_distinct_action = str(payload.get("next_distinct_action") or "")
    requested_execution_lane = str(payload.get("requested_execution_lane") or "")
    effective_execution_lane = str(payload.get("effective_execution_lane") or "")
    lane_fallback_reason = str(payload.get("lane_fallback_reason") or "")
    license_blocker_code = str(payload.get("license_blocker_code") or "")

    parts = ["[xuunity-mcp] request_failure"]
    if code:
        parts.append(f"code={code}")
    if request_submitted is not None:
        parts.append(f"request_submitted={str(bool(request_submitted)).lower()}")
    if request_ownership_acquired is not None:
        parts.append(f"request_ownership_acquired={str(bool(request_ownership_acquired)).lower()}")
    if request_id:
        parts.append(f"request_id={request_id}")
    if transport_outcome:
        parts.append(f"transport_outcome={transport_outcome}")
    if operation_outcome:
        parts.append(f"operation_outcome={operation_outcome}")
    if requested_execution_lane:
        parts.append(f"requested_execution_lane={requested_execution_lane}")
    if effective_execution_lane:
        parts.append(f"effective_execution_lane={effective_execution_lane}")
    if lane_fallback_reason:
        parts.append(f"lane_fallback_reason={lane_fallback_reason}")
    if license_blocker_code:
        parts.append(f"license_blocker_code={license_blocker_code}")
    if closeout_classification:
        parts.append(f"closeout_classification={closeout_classification}")
    if closeout_verified is not None:
        parts.append(f"closeout_verified={str(bool(closeout_verified)).lower()}")
    if process_visibility_error_code:
        parts.append(f"process_visibility_error_code={process_visibility_error_code}")
    if same_project_editor_closed is not None:
        parts.append(f"same_project_editor_closed={str(bool(same_project_editor_closed)).lower()}")
    if process_exit_verified is not None:
        parts.append(f"process_exit_verified={str(bool(process_exit_verified)).lower()}")
    if recommended_next_action:
        parts.append(f"recommended_next_action={recommended_next_action}")
    if next_distinct_action:
        parts.append(f"next_distinct_action={next_distinct_action}")

    try:
        sys.stderr.write(" ".join(parts) + "\n")
        if message:
            sys.stderr.write(f"[xuunity-mcp] error_message {message}\n")
        if recommended_recovery_command:
            sys.stderr.write(
                "[xuunity-mcp] recovery_command "
                f"{recommended_recovery_command}\n"
            )
        sys.stderr.flush()
    except Exception:
        pass


def build_registry_context_report() -> dict[str, Any]:
    return build_registry_context_report_data(
        list_active_project_contexts(),
        now=time.time(),
    )


def ensure_project_root(project_root: str) -> Path:
    return get_project_context(project_root).project_root


def bridge_operation_requires_request_lock(operation: str) -> bool:
    return str(operation or "").strip() in MUTATING_BRIDGE_OPERATIONS


def run_in_project_request_lock(
    context: ProjectContext,
    operation: str,
    callback: Callable[[], TProjectOperationResult],
) -> TProjectOperationResult:
    lock_scope = context.request_lock if bridge_operation_requires_request_lock(operation) else nullcontext()
    with lock_scope:
        return callback()


def current_project_context_bridge_state(project_root: Path) -> dict[str, Any]:
    context = refresh_project_context(project_root)
    return read_best_effort_bridge_state(project_root) or dict(context.last_bridge_state or {})


def current_project_context_host_session_state(project_root: Path) -> dict[str, Any]:
    context = refresh_project_context(project_root)
    return dict(context.last_host_editor_session_state or {})


def current_project_context_discovery_details(project_root: Path) -> dict[str, Any]:
    context = refresh_project_context(project_root)
    details = context.discovery_details if isinstance(getattr(context, "discovery_details", None), dict) else {}
    return dict(details or {})


def build_project_discovery_report(project_root: Path) -> dict[str, Any]:
    context = refresh_project_context(project_root)
    discovery = current_project_context_discovery_details(project_root)
    return build_project_discovery_report_data(
        project_root,
        context=context,
        discovery=discovery,
    )


RECOVERY_RECONCILIATION_ACTIONS = frozenset(
    {
        "ensure_ready_or_recover_bridge",
        "wait_for_bridge_or_recover_editor",
        "recover_editor_session",
        "open_editor_or_ensure_ready",
        "start_or_recover_editor",
        "clear_stale_host_session_and_retry",
    }
)


def build_status_summary_from_context(
    project_root: Path,
    payload: dict[str, Any],
    *,
    include_full_payload: bool = True,
) -> dict[str, Any]:
    return build_status_summary(
        project_root,
        payload if isinstance(payload, dict) else {},
        read_best_effort_bridge_state=current_project_context_bridge_state,
        try_read_bridge_state=lambda path: dict(refresh_project_context(path).last_bridge_state or {}),
        pid_is_alive=pid_is_alive,
        heartbeat_age_seconds=heartbeat_age_seconds,
        derive_busy_reason=derive_busy_reason,
        summarize_state_for_error=summarize_state_for_error,
        discovery_details=current_project_context_discovery_details(project_root),
        include_full_payload=include_full_payload,
    )


DISCOVERY_STATUS_FALLBACK_ERROR_CODES = frozenset(
    {
        "editor_not_running",
        "process_visibility_restricted",
        "process_visibility_restricted_before_open",
        "transport_not_ready",
        "bridge_disabled",
    }
)

SCENARIO_RECOVERY_ERROR_CODES = frozenset(
    {
        "editor_not_running",
        "transport_not_ready",
        "transport_connect_failed",
        "transport_response_missing",
        "request_lifecycle_reset",
        "response_missing_after_lifecycle_reset",
    }
)


DISCOVERY_NEXT_ACTION_COMMANDS = {
    "enable_bridge_and_retry": "init_xuunity_light_unity_mcp.sh --project-root {project_root} --enable-project",
    "open_editor_or_ensure_ready": "xuunity_light_unity_mcp.sh ensure-ready --project-root {project_root} --open-editor",
    "ensure_ready_or_recover_bridge": "xuunity_light_unity_mcp.sh ensure-ready --project-root {project_root} --open-editor",
    "wait_for_bridge_or_recover_editor": "xuunity_light_unity_mcp.sh recover-editor-session --project-root {project_root} --timeout-ms 180000",
    "recover_editor_session": "xuunity_light_unity_mcp.sh recover-editor-session --project-root {project_root} --timeout-ms 180000",
    "close_same_project_editor_or_use_interactive_lane": "xuunity_light_unity_mcp.sh request-editor-quit --project-root {project_root} --timeout-ms 30000 --wait-for-exit --exit-timeout-ms 30000",
    "start_or_recover_editor": "xuunity_light_unity_mcp.sh ensure-ready --project-root {project_root} --open-editor",
    "clear_stale_host_session_and_retry": "xuunity_light_unity_mcp.sh restore-editor-state --project-root {project_root} --timeout-ms 15000",
    "refresh_host_session_if_needed": "xuunity_light_unity_mcp.sh request-status-summary --project-root {project_root} --timeout-ms 5000",
    "inspect_editor_log": "xuunity_light_unity_mcp.sh project-discovery-report --project-root {project_root}",
    "inspect_editor_log_and_observe": "xuunity_light_unity_mcp.sh project-discovery-report --project-root {project_root}",
    "inspect_editor_log_and_consider_graceful_restart": "xuunity_light_unity_mcp.sh ensure-ready --project-root {project_root} --open-editor",
    "relaunch_noninteractive_accept_apiupdate": "Unity -batchmode -quit -accept-apiupdate -projectPath {project_root} -logFile {project_root}/Library/XUUnityLightMcp/logs/unity_apiupdate.log",
    "restore_host_process_visibility": "xuunity_light_unity_mcp.sh project-discovery-report --project-root {project_root}",
}


def recommended_recovery_command_for_project(project_root: Path, next_action: str) -> str:
    template = DISCOVERY_NEXT_ACTION_COMMANDS.get(str(next_action or "").strip())
    if not template:
        return ""
    return template.format(project_root=project_root.as_posix())


def enrich_error_details_with_discovery(project_root: Path, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return enrich_error_details_with_discovery_data(
        project_root,
        details=details,
        discovery=current_project_context_discovery_details(project_root),
        recommended_recovery_command_for_project=recommended_recovery_command_for_project,
    )


def enrich_tool_invocation_error_with_discovery(project_root: Path, exc: ToolInvocationError) -> ToolInvocationError:
    return ToolInvocationError(
        exc.code,
        exc.message,
        enrich_error_details_with_discovery(project_root, exc.details),
    )
