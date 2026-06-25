# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import json
import time
import subprocess
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable, TypeVar

# Registry type re-exports
from server_registry import (
    ProjectContext,
    get_project_context,
    refresh_project_context,
    list_active_project_contexts,
    forget_project_context,
    prune_stale_project_contexts,
)

# Core imports
from server_core import ToolInvocationError, read_json, write_json
from server_specs import (
    OPERATION_LIFECYCLE_POLICIES,
    SCENARIO_DEFINITION_SCHEMA,
    SCENARIO_TERMINAL_STATUSES,
    STARTUP_POLICIES,
    TOOLS,
)
from server_health import (
    FRESH_HEARTBEAT_MAX_AGE_SECONDS,
    build_editor_log_diagnosis,
    classify_project_health,
)
from server_license import (
    build_license_capabilities,
    classify_license_log,
)
from server_loading_timing import request_loading_timing_summary
from server_host_platform import current_host_platform_adapter
from server_mcp_protocol import (
    JsonRpcError,
    build_initialize_result as build_initialize_result_base,
    handle_json_rpc_message as handle_json_rpc_message_base,
    list_tools_result as list_tools_result_base,
    serve_stdio as serve_stdio_base,
)
from server_mcp_tools import (
    call_tool as call_tool_base,
    call_unity_compile_build_config_matrix_tool as call_unity_compile_build_config_matrix_tool_base,
    call_unity_maintenance_prune_tool as call_unity_maintenance_prune_tool_base,
    call_unity_request_final_status_tool as call_unity_request_final_status_tool_base,
    call_unity_scenario_result_summary_tool as call_unity_scenario_result_summary_tool_base,
    call_unity_scenario_run_and_wait_tool as call_unity_scenario_run_and_wait_tool_base,
    call_unity_status_summary_tool as call_unity_status_summary_tool_base,
)
from server_bridge_payloads import (
    bridge_response_to_tool_result as bridge_response_to_tool_result_data,
    normalize_response_payload_from_lifecycle as normalize_response_payload_from_lifecycle_data,
    scenario_failure_tool_result as scenario_failure_tool_result_data,
    _decode_bridge_payload_dict,
    _bridge_error_code,
)
from server_bridge_runtime import (
    DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
    DEFAULT_IDLE_STABLE_CYCLES,
    active_scenario_run_path,
    annotate_bridge_state_with_liveness,
    build_bridge_stabilization_summary,
    build_request_final_status,
    bridge_enabled,
    bridge_identity_from_state,
    bridge_root,
    bridge_state_path,
    cancel_request_best_effort,
    captures_dir,
    cleanup_stale_request_artifacts,
    default_editor_log_path,
    derive_busy_reason,
    expected_playmode_state_for_action,
    fail_if_compile_broken_for_operation,
    heartbeat_age_seconds,
    inspect_stale_request_artifacts,
    inspect_bridge_state_liveness,
    invoke_bridge_transport,
    logs_dir,
    maybe_record_settle_lifecycle_transition,
    pid_is_alive,
    read_best_effort_bridge_state,
    read_request_journal_events,
    report_operation_progress_phase,
    request_journal_dir,
    scenario_results_dir,
    summarize_state_for_error,
    try_read_bridge_state,
    try_read_live_editor_state,
    wait_for_editor_idle,
    wait_for_playmode_state,
)
from server_editor_host import (
    activate_unity_editor,
    bridge_state_is_ready,
    build_batch_validation_command,
    build_plain_batch_build_command,
    classify_editor_log,
    clear_stale_bridge_state,
    clear_stale_project_lock,
    default_batch_build_log_path,
    default_batch_operation_log_path,
    default_batch_operation_result_path,
    default_batch_build_result_path,
    detect_unity_app_path_for_project,
    find_running_unity_editors_for_project,
    list_live_project_editor_pids,
    open_unity_editor,
    process_visibility_summary,
    read_recent_editor_log,
    resolve_batch_build_output_path,
    resolve_editor_log_path,
    restore_host_opened_editor_state,
    terminate_editor_pid,
    try_read_host_editor_session_state,
    update_host_editor_session_pid,
    verify_project_editor_closed,
    wait_for_ready,
)
from server_project_reporting import (
    apply_discovery_to_final_status_summary_data,
    apply_discovery_to_scenario_payload_data,
    build_discovery_scenario_result_summary_for_error_data,
    build_discovery_status_summary_for_error_data,
    build_project_discovery_report_data,
    build_registry_context_report_data,
    build_request_final_status_from_context_data,
    build_scenario_result_summary_from_context_data,
    enrich_error_details_with_discovery_data,
)
from server_registry import BridgeRegistry
from server_scenario_polling import (
    is_terminal_scenario_status as is_terminal_scenario_status_data,
    wait_for_scenario_result_data,
)
from server_summaries import (
    build_scenario_decision_verdict,
    build_scenario_result_summary,
    build_status_summary,
    normalize_scenario_payload,
    prune_project_artifacts,
    try_read_json_dict,
    truncate_text,
)
from server_workspace_effects import (
    build_workspace_side_effects,
    capture_git_dirty_paths,
    load_side_effect_allow_file,
    unavailable_workspace_side_effects,
)

# Setup wizard, project context and metadata wrappers
from server_project_context import (
    ensure_project_root as ensure_project_root_base,
    find_latest_request_event,
    find_repo_local_package_source,
    inspect_package_dependency_alignment,
)
from server_setup_wizard import (
    LIGHT_MCP_PACKAGE_NAME as SETUP_LIGHT_MCP_PACKAGE_NAME,
    TEST_FRAMEWORK_CAPABILITY_DEFINE,
    TEST_FRAMEWORK_PACKAGE_NAME,
    apply_uninstall_plan,
    apply_setup_plan,
    build_uninstall_plan,
    build_setup_plan,
    classify_test_framework_state,
    install_test_framework,
    normalize_project_root as normalize_setup_project_root,
    parse_unity_version,
    validate_setup,
)
from server_scenario_results import (
    latest_persisted_scenario_result_summary,
    list_persisted_scenario_result_summaries,
    reconcile_persisted_scenario_result as reconcile_persisted_scenario_result_data,
)
from server_operation_evidence import (
    attach_operation_evidence_to_payload,
    attach_persisted_scenario_result_evidence,
    parse_utc_timestamp,
)
from server_project_actions import (
    build_project_action_invocation_payload,
    build_project_action_scenario,
    load_project_action_catalog,
    normalize_project_action_scenario,
    project_action_catalog_payload,
    resolve_project_action,
    scaffold_project_hook,
)
from server_build_config import build_compile_matrix_args_from_build_config
from server_batch_reporting import (
    DEFAULT_BATCH_PROGRESS_INTERVAL_SECONDS,
    BatchProgressReporter,
    attach_batch_summary_to_error,
    batch_summary_artifact_path,
    build_batch_execution_summary,
    build_batch_prepare_failure_summary,
    build_batch_run_id,
    run_subprocess_with_progress,
    write_batch_summary_artifact,
    batch_progress_sidecar_path,
    first_non_empty_line,
)
from server_runtime_config import (
    resolve_operation_default_timeout_ms,
    resolve_operation_lifecycle_policy_overrides,
)
from server_artifact_probe import load_artifact_probe_config, run_artifact_probe
from server_artifact_registry import register_artifact, write_artifact_report

# ProcessLauncher for self-invocation
from server_process_launcher import ProcessLauncher

# Protocol metadata
PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {
    "name": "xuunity-mcp",
    "version": "0.3.32",
}

# === Block A: Registry & Discovery Helpers ===
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
    "restore_host_process_visibility": "xuunity_light_unity_mcp.sh project-discovery-report --project-root {project_root}",
}


def recommended_recovery_command_for_project(project_root: Path, next_action: str) -> str:
    template = DISCOVERY_NEXT_ACTION_COMMANDS.get(str(next_action or "").strip())
    if not template:
        return ""
    return template.format(project_root=str(project_root))


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
) -> dict[str, Any]:
    before_state = current_project_context_bridge_state(project_root)
    discovery = current_project_context_discovery_details(project_root)
    termination_policy = str(discovery.get("host_health_termination_policy") or "observe_only")
    health_classification = str(discovery.get("host_health_classification") or "")
    result: dict[str, Any] = {
        "host_health_classification": health_classification,
        "termination_policy": termination_policy,
        "action": "none",
    }

    if health_classification not in {"anr", "anr_suspected"}:
        return result

    if termination_policy == "observe_only":
        result["action"] = "observe_only"
        return result

    candidate_pid = 0
    for value in (
        int(discovery.get("bridge_pid") or 0),
        int(discovery.get("host_session_pid") or 0),
    ):
        if value > 0:
            candidate_pid = value
            break
    if candidate_pid <= 0:
        detected_pids = list(discovery.get("detected_editor_pids") or [])
        candidate_pid = int(detected_pids[0] or 0) if detected_pids else 0

    if candidate_pid <= 0:
        result["action"] = "no_live_pid_for_termination"
        return result

    result["target_editor_pid"] = candidate_pid
    if not allow_open_editor:
        result["action"] = "termination_deferred_no_open"
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
) -> dict[str, Any]:
    current_state = current_project_context_bridge_state(project_root)
    discovery = current_project_context_discovery_details(project_root)
    next_action = str(discovery.get("reconciliation_recommended_next_action") or "")

    recovery: dict[str, Any] = {
        "reconciliation_case": str(discovery.get("reconciliation_case") or ""),
        "reconciliation_status": str(discovery.get("reconciliation_status") or ""),
        "reconciliation_recommended_next_action": next_action,
        "allow_open_editor": allow_open_editor,
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
    )
    recovery["host_health_recovery"] = host_health_recovery
    if str(host_health_recovery.get("action") or "") in {
        "terminated_editor",
        "terminated_and_reopened",
        "termination_failed",
        "no_live_pid_for_termination",
        "termination_deferred_no_open",
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
            "xuunity_light_unity_mcp.sh request-editor-quit --project-root {project_root} --timeout-ms 30000 --wait-for-exit --exit-timeout-ms 30000",
        )

    return (
        "compile_red_confirmed",
        "fix_compile_errors_before_gui_reopen",
        "xuunity_light_unity_mcp.sh project-discovery-report --project-root {project_root}",
    )


def run_self_json_command_with_completed(args: list[str]) -> tuple[dict[str, Any] | None, subprocess.CompletedProcess[str]]:
    completed = subprocess.run(
        ProcessLauncher.get_self_invocation_base_command() + [ *args],
        check=False,
        capture_output=True,
        text=True,
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


# === Block B: Bridge, Tool, MCP Stdio Helpers ===

def request_editor_quit(project_root: Path, timeout_ms: int) -> dict[str, Any]:
    return invoke_bridge(project_root, "unity.editor.quit", {}, timeout_ms)

def wait_for_scenario_result(
    project_root: Path,
    run_id: str,
    scenario_name: str,
    timeout_ms: int,
    poll_interval_ms: int,
) -> dict[str, Any]:
    return wait_for_scenario_result_data(
        project_root,
        run_id,
        scenario_name,
        timeout_ms,
        poll_interval_ms,
        scenario_recovery_error_codes=SCENARIO_RECOVERY_ERROR_CODES,
        scenario_terminal_statuses=SCENARIO_TERMINAL_STATUSES,
        default_heartbeat_max_age_seconds=DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
        try_read_live_editor_state=try_read_live_editor_state,
        activate_unity_editor=activate_unity_editor,
        invoke_bridge=invoke_bridge,
        recover_project_bridge_for_reconciliation=recover_project_bridge_for_reconciliation,
        current_project_context_bridge_state=current_project_context_bridge_state,
        enrich_tool_invocation_error_with_discovery=enrich_tool_invocation_error_with_discovery,
        bridge_response_to_tool_result=bridge_response_to_tool_result,
        normalize_scenario_payload=normalize_scenario_payload,
        apply_discovery_to_scenario_payload=apply_discovery_to_scenario_payload,
        reconcile_persisted_scenario_result=reconcile_persisted_scenario_result,
        tool_invocation_error_type=ToolInvocationError,
    )


def reconcile_persisted_scenario_result(
    project_root: Path,
    run_id: str,
    scenario_name: str,
) -> dict[str, Any]:
    return reconcile_persisted_scenario_result_data(
        project_root,
        scenario_results_dir=scenario_results_dir,
        read_json=read_json,
        parse_utc_timestamp=parse_utc_timestamp,
        scenario_terminal_statuses=SCENARIO_TERMINAL_STATUSES,
        run_id=run_id,
        scenario_name=scenario_name,
    )

def is_terminal_scenario_status(status: Any) -> bool:
    return is_terminal_scenario_status_data(status, SCENARIO_TERMINAL_STATUSES)


def normalize_response_payload_from_lifecycle(response: dict[str, Any], lifecycle: dict[str, Any]) -> dict[str, Any]:
    return normalize_response_payload_from_lifecycle_data(
        response,
        lifecycle,
        normalize_scenario_payload=normalize_scenario_payload,
        scenario_terminal_statuses=SCENARIO_TERMINAL_STATUSES,
    )


def resolve_operation_timeout_ms(
    project_root: Path,
    operation: str,
    explicit_timeout_ms: Any,
    fallback_timeout_ms: int,
) -> int:
    if isinstance(explicit_timeout_ms, int):
        return explicit_timeout_ms
    if explicit_timeout_ms is not None:
        raise JsonRpcError(-32602, "timeoutMs must be an integer.")
    return resolve_operation_default_timeout_ms(project_root, operation, fallback_timeout_ms)


def resolve_operation_lifecycle_policy(project_root: Path, operation: str) -> dict[str, Any]:
    policy = {
        "activate_unity": False,
        "wait_for_idle_before": False,
        "wait_for_idle_after": False,
        "idle_stable_cycles_after": DEFAULT_IDLE_STABLE_CYCLES,
        "retry_on_lifecycle_reset": False,
        "retry_on_transport_response_missing": False,
        "retry_on_transport_connect_failed": False,
        "post_reset_recovery_cap_ms": 0,
    }
    policy.update(OPERATION_LIFECYCLE_POLICIES.get(operation, {}))
    policy.update(resolve_operation_lifecycle_policy_overrides(project_root, operation))
    return policy


def invoke_bridge(project_root_value: str, operation: str, args: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    context = get_project_context(project_root_value)
    project_root = context.project_root

    def perform_invoke() -> dict[str, Any]:
        policy = resolve_operation_lifecycle_policy(project_root, operation)
        max_attempts = 2 if (
            bool(policy.get("retry_on_lifecycle_reset"))
            or bool(policy.get("retry_on_transport_response_missing"))
            or bool(policy.get("retry_on_transport_connect_failed"))
        ) else 1

        for attempt_index in range(max_attempts):
            pre_request_state = try_read_live_editor_state(project_root) or current_project_context_bridge_state(project_root)
            progress_enabled = bool(
                policy.get("activate_unity")
                or policy.get("wait_for_idle_before")
                or policy.get("wait_for_idle_after")
            )
            lifecycle: dict[str, Any] = {
                "operation": operation,
                "attempt_index": attempt_index,
                "max_attempts": max_attempts,
                "activation_requested": False,
                "idle_wait_before": None,
                "idle_wait_after": None,
                "transport": None,
                "bridge_identity_before_request": {
                    "bridge_generation": bridge_identity_from_state(pre_request_state)[0],
                    "bridge_session_id": bridge_identity_from_state(pre_request_state)[1],
                },
            }

            try:
                if policy["activate_unity"]:
                    report_operation_progress_phase(
                        project_root=project_root,
                        operation=operation,
                        phase="activation",
                        state=pre_request_state,
                    )
                    lifecycle["activation_requested"] = True
                    lifecycle["activation"] = recover_project_bridge_for_reconciliation(
                        project_root,
                        timeout_ms=min(timeout_ms, 180000),
                        heartbeat_max_age_seconds=DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
                        startup_policy=str(
                            pre_request_state.get("startup_policy")
                            or "fail_fast_on_interactive_compile_block"
                        ),
                        allow_open_editor=True,
                    )

                pre_idle_state = try_read_live_editor_state(project_root) or current_project_context_bridge_state(project_root)
                fail_if_compile_broken_for_operation(project_root, operation, pre_idle_state)

                if policy["wait_for_idle_before"]:
                    report_operation_progress_phase(
                        project_root=project_root,
                        operation=operation,
                        phase="wait_for_idle_before",
                        state=pre_idle_state,
                    )
                    lifecycle["idle_wait_before"] = wait_for_editor_idle(
                        project_root,
                        timeout_ms,
                        DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
                        f"before {operation}",
                        stable_cycles=1,
                    )

                dispatch_state = try_read_live_editor_state(project_root) or current_project_context_bridge_state(project_root)
                if progress_enabled:
                    report_operation_progress_phase(
                        project_root=project_root,
                        operation=operation,
                        phase="dispatching",
                        state=dispatch_state,
                    )
                    report_operation_progress_phase(
                        project_root=project_root,
                        operation=operation,
                        phase="waiting_for_response",
                        state=dispatch_state,
                    )
                response, request_id, request_started_at, transport_metadata = invoke_bridge_transport(
                    project_root,
                    operation,
                    args,
                    timeout_ms,
                    post_reset_recovery_cap_ms=int(policy.get("post_reset_recovery_cap_ms") or 0),
                )
                lifecycle["transport"] = transport_metadata

                if operation == "unity.playmode.set":
                    expected_playmode_state = expected_playmode_state_for_action(str(args.get("action") or ""))
                    if expected_playmode_state:
                        report_operation_progress_phase(
                            project_root=project_root,
                            operation=operation,
                            phase="wait_for_idle_after",
                            request_id=request_id,
                            state=try_read_live_editor_state(project_root) or current_project_context_bridge_state(project_root),
                            detail=f"playmode_target:{expected_playmode_state}",
                        )
                        lifecycle["playmode_wait_after"] = wait_for_playmode_state(
                            project_root,
                            timeout_ms,
                            DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
                            expected_playmode_state,
                            f"after {operation}",
                            after_request_id=request_id,
                            not_before_unix=request_started_at,
                            stable_cycles=int(policy["idle_stable_cycles_after"]),
                        )
                    elif policy["wait_for_idle_after"]:
                        report_operation_progress_phase(
                            project_root=project_root,
                            operation=operation,
                            phase="wait_for_idle_after",
                            request_id=request_id,
                            state=try_read_live_editor_state(project_root) or current_project_context_bridge_state(project_root),
                        )
                        lifecycle["idle_wait_after"] = wait_for_editor_idle(
                            project_root,
                            timeout_ms,
                            DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
                            f"after {operation}",
                            after_request_id=request_id,
                            not_before_unix=request_started_at,
                            stable_cycles=int(policy["idle_stable_cycles_after"]),
                        )
                elif policy["wait_for_idle_after"]:
                    report_operation_progress_phase(
                        project_root=project_root,
                        operation=operation,
                        phase="wait_for_idle_after",
                        request_id=request_id,
                        state=try_read_live_editor_state(project_root) or current_project_context_bridge_state(project_root),
                    )
                    lifecycle["idle_wait_after"] = wait_for_editor_idle(
                        project_root,
                        timeout_ms,
                        DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
                        f"after {operation}",
                        after_request_id=request_id,
                        not_before_unix=request_started_at,
                        stable_cycles=int(policy["idle_stable_cycles_after"]),
                    )

                settled_state = (
                    lifecycle.get("playmode_wait_after")
                    if isinstance(lifecycle.get("playmode_wait_after"), dict)
                    else lifecycle.get("idle_wait_after")
                )
                if isinstance(settled_state, dict):
                    transition = maybe_record_settle_lifecycle_transition(
                        project_root,
                        operation,
                        request_id,
                        pre_request_state,
                        settled_state,
                    )
                    if transition:
                        lifecycle["bridge_identity_transition"] = transition

                if response.get("status") == "ok":
                    response = normalize_response_payload_from_lifecycle(dict(response), lifecycle)
                    payload_json = response.get("payload_json")
                    if isinstance(payload_json, str) and payload_json:
                        try:
                            parsed_payload = json.loads(payload_json)
                        except json.JSONDecodeError:
                            parsed_payload = None
                        if isinstance(parsed_payload, dict):
                            journal_events = read_request_journal_events(project_root, request_id)
                            response["payload_json"] = json.dumps(
                                attach_operation_evidence_to_payload(
                                    parsed_payload,
                                    project_root=project_root,
                                    operation=operation,
                                    request_id=request_id,
                                    request_submitted_at_utc=next(
                                        (
                                            str(event.get("event_at_utc") or "")
                                            for event in reversed(journal_events)
                                            if str(event.get("event_type") or "") == "request_submitted"
                                        ),
                                        "",
                                    ),
                                    request_started_at_utc=next(
                                        (
                                            str(event.get("started_at_utc") or event.get("event_at_utc") or "")
                                            for event in journal_events
                                            if str(event.get("event_type") or "") == "request_started"
                                        ),
                                        "",
                                    ),
                                    request_completed_at_utc=next(
                                        (
                                            str(event.get("completed_at_utc") or event.get("event_at_utc") or "")
                                            for event in reversed(journal_events)
                                            if str(event.get("event_type") or "") == "request_completed"
                                        ),
                                        "",
                                    ),
                                    response_completed_at_utc=str(response.get("completed_at_utc") or ""),
                                    editor_log_path=default_editor_log_path(project_root),
                                    journal_event_paths=[str(event.get("_path") or "") for event in journal_events],
                                    lifecycle=lifecycle,
                                    host_started_unix=request_started_at,
                                    host_completed_unix=time.time(),
                                ),
                                ensure_ascii=True,
                                separators=(",", ":"),
                            )
                    response["_xuunity_lifecycle"] = lifecycle

                refresh_project_context(project_root)
                return response
            except ToolInvocationError as exc:
                if exc.code == "request_lifecycle_reset" and attempt_index + 1 < max_attempts:
                    lifecycle["lifecycle_reset_retry"] = exc.details
                    lifecycle["lifecycle_reset_recovery"] = recover_project_bridge_for_reconciliation(
                        project_root,
                        timeout_ms=min(timeout_ms, 10000),
                        heartbeat_max_age_seconds=DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
                        startup_policy=str(
                            (current_project_context_bridge_state(project_root) or pre_request_state or {}).get("startup_policy")
                            or "fail_fast_on_interactive_compile_block"
                        ),
                        allow_open_editor=False,
                    )
                    continue
                if (
                    exc.code == "transport_response_missing"
                    and bool(policy.get("retry_on_transport_response_missing"))
                    and attempt_index + 1 < max_attempts
                    and not bool((exc.details or {}).get("request_processed"))
                ):
                    lifecycle["transport_response_missing_retry"] = exc.details
                    lifecycle["transport_response_missing_recovery"] = recover_project_bridge_for_reconciliation(
                        project_root,
                        timeout_ms=min(timeout_ms, 10000),
                        heartbeat_max_age_seconds=DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
                        startup_policy=str(
                            (current_project_context_bridge_state(project_root) or pre_request_state or {}).get("startup_policy")
                            or "fail_fast_on_interactive_compile_block"
                        ),
                        allow_open_editor=False,
                    )
                    continue
                if (
                    exc.code == "transport_connect_failed"
                    and bool(policy.get("retry_on_transport_connect_failed"))
                    and attempt_index + 1 < max_attempts
                ):
                    lifecycle["transport_connect_failed_retry"] = exc.details
                    retry_state = current_project_context_bridge_state(project_root) or pre_request_state or {}
                    lifecycle["transport_connect_failed_recovery"] = recover_project_bridge_for_reconciliation(
                        project_root,
                        timeout_ms=min(timeout_ms, 10000),
                        heartbeat_max_age_seconds=DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
                        startup_policy=str(
                            retry_state.get("startup_policy")
                            or "fail_fast_on_interactive_compile_block"
                        ),
                        allow_open_editor=False,
                    )
                    continue
                raise enrich_tool_invocation_error_with_discovery(project_root, exc)

        raise ToolInvocationError("unreachable", f"Unexpected lifecycle retry state for {operation}.")

    return run_in_project_request_lock(context, operation, perform_invoke)

def bridge_response_to_tool_result(response: dict[str, Any]) -> dict[str, Any]:
    return bridge_response_to_tool_result_data(
        response,
        normalize_scenario_payload=normalize_scenario_payload,
        scenario_terminal_statuses=SCENARIO_TERMINAL_STATUSES,
    )


def scenario_failure_tool_result(result_payload: dict[str, Any]) -> dict[str, Any]:
    return scenario_failure_tool_result_data(result_payload)


def call_unity_compile_build_config_matrix_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    return call_unity_compile_build_config_matrix_tool_base(
        arguments,
        tool_invocation_error_type=ToolInvocationError,
        ensure_project_root=ensure_project_root,
        resolve_operation_timeout_ms=resolve_operation_timeout_ms,
        build_compile_matrix_args_from_build_config=build_compile_matrix_args_from_build_config,
        invoke_bridge=invoke_bridge,
        build_tool_error_payload=build_tool_error_payload,
        bridge_response_to_tool_result=bridge_response_to_tool_result,
    )


def call_unity_scenario_run_and_wait_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        arguments = normalize_scenario_tool_arguments(arguments)
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return call_unity_scenario_run_and_wait_tool_base(
        arguments,
        tool_invocation_error_type=ToolInvocationError,
        ensure_project_root=ensure_project_root,
        resolve_operation_timeout_ms=resolve_operation_timeout_ms,
        invoke_bridge=invoke_bridge,
        bridge_response_to_tool_result=bridge_response_to_tool_result,
        wait_for_scenario_result=wait_for_scenario_result,
        build_scenario_decision_verdict=build_scenario_decision_verdict,
        scenario_terminal_statuses=SCENARIO_TERMINAL_STATUSES,
        build_tool_error_payload=build_tool_error_payload,
        scenario_failure_tool_result=scenario_failure_tool_result,
    )


def normalize_scenario_tool_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    scenario = arguments.get("scenario")
    if not isinstance(project_root_value, str) or not project_root_value.strip() or not isinstance(scenario, dict):
        return arguments

    project_root = ensure_project_root(project_root_value)
    normalized = dict(arguments)
    normalized["projectRoot"] = str(project_root)
    normalized["scenario"] = normalize_project_action_scenario(
        project_root=project_root,
        scenario=scenario,
    )
    return normalized


def call_unity_scenario_validate_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        arguments = normalize_scenario_tool_arguments(arguments)
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")
    scenario = arguments.get("scenario")
    if not isinstance(scenario, dict):
        raise JsonRpcError(-32602, "scenario must be an object.")

    timeout_ms = arguments.get("timeoutMs", 5000)
    if not isinstance(timeout_ms, int):
        raise JsonRpcError(-32602, "timeoutMs must be an integer.")

    try:
        project_root = ensure_project_root(project_root_value)
        response = invoke_bridge(str(project_root), "unity.scenario.validate", {"scenario": scenario}, timeout_ms)
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return bridge_response_to_tool_result(response)


def _optional_string_list_argument(arguments: dict[str, Any], key: str) -> list[str]:
    value = arguments.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise JsonRpcError(-32602, f"{key} must be an array of strings when provided.")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise JsonRpcError(-32602, f"{key} must be an array of strings when provided.")
        text = item.strip()
        if text:
            normalized.append(text)
    return normalized


def call_unity_loading_timing_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")

    timeout_ms = arguments.get("timeoutMs", 5000)
    if not isinstance(timeout_ms, int):
        raise JsonRpcError(-32602, "timeoutMs must be an integer.")

    limit = arguments.get("limit", 20)
    if not isinstance(limit, int):
        raise JsonRpcError(-32602, "limit must be an integer.")

    timing_only = arguments.get("timingOnly", True)
    if not isinstance(timing_only, bool):
        raise JsonRpcError(-32602, "timingOnly must be a boolean.")

    include_stack_traces = arguments.get("includeStackTraces", False)
    if not isinstance(include_stack_traces, bool):
        raise JsonRpcError(-32602, "includeStackTraces must be a boolean.")

    markers = _optional_string_list_argument(arguments, "markers")
    include_types = _optional_string_list_argument(arguments, "includeTypes")

    try:
        project_root = ensure_project_root(project_root_value)
        summary = request_loading_timing_summary(
            project_root=project_root,
            markers=markers,
            timing_only=timing_only,
            include_stack_traces=include_stack_traces,
            include_types=include_types,
            limit=limit,
            timeout_ms=timeout_ms,
            invoke_bridge=invoke_bridge,
        )
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return mcp_json_result(summary, is_error=not bool(summary.get("succeeded")))


def call_unity_scenario_run_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        arguments = normalize_scenario_tool_arguments(arguments)
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")
    scenario = arguments.get("scenario")
    if not isinstance(scenario, dict):
        raise JsonRpcError(-32602, "scenario must be an object.")

    try:
        project_root = ensure_project_root(project_root_value)
        timeout_ms = resolve_operation_timeout_ms(
            project_root,
            "unity.scenario.run",
            arguments.get("timeoutMs"),
            5000,
        )
        response = invoke_bridge(str(project_root), "unity.scenario.run", {"scenario": scenario}, timeout_ms)
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return bridge_response_to_tool_result(response)


def call_unity_status_summary_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")

    timeout_ms = arguments.get("timeoutMs", 5000)
    if not isinstance(timeout_ms, int):
        raise JsonRpcError(-32602, "timeoutMs must be an integer.")

    project_root = ensure_project_root(project_root_value)
    try:
        response = invoke_bridge(str(project_root), "unity.status", {}, timeout_ms)
    except ToolInvocationError as exc:
        if exc.code in DISCOVERY_STATUS_FALLBACK_ERROR_CODES:
            summary = build_discovery_status_summary_for_error(project_root, exc)
            return {
                "content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=True)}],
                "structuredContent": summary,
                "isError": False,
            }
        return {
            "content": [{"type": "text", "text": json.dumps(build_tool_error_payload(exc), ensure_ascii=True)}],
            "structuredContent": build_tool_error_payload(exc),
            "isError": True,
        }

    tool_result = bridge_response_to_tool_result(response)
    if tool_result.get("isError"):
        return tool_result

    payload = tool_result.get("structuredContent") or {}
    summary = build_status_summary_from_context(project_root, payload if isinstance(payload, dict) else {})
    return {
        "content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=True)}],
        "structuredContent": summary,
        "isError": False,
    }


def call_unity_request_final_status_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    return call_unity_request_final_status_tool_base(
        arguments,
        ensure_project_root=ensure_project_root,
        build_request_final_status_summary=build_request_final_status_from_context,
    )


def call_unity_scenario_result_summary_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")

    timeout_ms = arguments.get("timeoutMs", 5000)
    if not isinstance(timeout_ms, int):
        raise JsonRpcError(-32602, "timeoutMs must be an integer.")

    project_root = ensure_project_root(project_root_value)
    bridge_args: dict[str, Any] = {}
    run_id = arguments.get("runId")
    if isinstance(run_id, str) and run_id.strip():
        bridge_args["runId"] = run_id.strip()
    scenario_name = arguments.get("scenarioName")
    if isinstance(scenario_name, str) and scenario_name.strip():
        bridge_args["scenarioName"] = scenario_name.strip()

    try:
        response = invoke_bridge(str(project_root), "unity.scenario.result", bridge_args, timeout_ms)
    except ToolInvocationError as exc:
        if exc.code in DISCOVERY_STATUS_FALLBACK_ERROR_CODES.union(SCENARIO_RECOVERY_ERROR_CODES):
            summary = build_discovery_scenario_result_summary_for_error(
                project_root,
                bridge_args.get("runId", ""),
                bridge_args.get("scenarioName", ""),
                exc,
            )
            return {
                "content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=True)}],
                "structuredContent": summary,
                "isError": False,
            }
        return {
            "content": [{"type": "text", "text": json.dumps(build_tool_error_payload(exc), ensure_ascii=True)}],
            "structuredContent": build_tool_error_payload(exc),
            "isError": True,
        }

    tool_result = bridge_response_to_tool_result(response)
    if tool_result.get("isError"):
        return tool_result

    payload = tool_result.get("structuredContent") or {}
    summary = build_scenario_result_summary_from_context(project_root, payload if isinstance(payload, dict) else {})
    return {
        "content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=True)}],
        "structuredContent": summary,
        "isError": False,
    }


def call_unity_scenario_results_list_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")

    scenario_name = arguments.get("scenarioName")
    if scenario_name is not None and not isinstance(scenario_name, str):
        raise JsonRpcError(-32602, "scenarioName must be a string when provided.")

    limit = arguments.get("limit", 20)
    if not isinstance(limit, int):
        raise JsonRpcError(-32602, "limit must be an integer.")

    project_root = ensure_project_root(project_root_value)
    result = list_persisted_scenario_result_summaries(
        project_root,
        scenario_results_dir=scenario_results_dir,
        read_json=read_json,
        parse_utc_timestamp=parse_utc_timestamp,
        attach_persisted_scenario_result_evidence=attach_persisted_scenario_result_evidence,
        build_scenario_result_summary=build_scenario_result_summary,
        scenario_terminal_statuses=SCENARIO_TERMINAL_STATUSES,
        scenario_name=scenario_name.strip() if isinstance(scenario_name, str) else "",
        limit=limit,
    )
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=True)}],
        "structuredContent": result,
        "isError": False,
    }


def call_unity_scenario_result_latest_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")

    scenario_name = arguments.get("scenarioName")
    if scenario_name is not None and not isinstance(scenario_name, str):
        raise JsonRpcError(-32602, "scenarioName must be a string when provided.")

    project_root = ensure_project_root(project_root_value)
    result = latest_persisted_scenario_result_summary(
        project_root,
        scenario_results_dir=scenario_results_dir,
        read_json=read_json,
        parse_utc_timestamp=parse_utc_timestamp,
        attach_persisted_scenario_result_evidence=attach_persisted_scenario_result_evidence,
        build_scenario_result_summary=build_scenario_result_summary,
        scenario_terminal_statuses=SCENARIO_TERMINAL_STATUSES,
        scenario_name=scenario_name.strip() if isinstance(scenario_name, str) else "",
    )
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=True)}],
        "structuredContent": result,
        "isError": False,
    }


def call_unity_maintenance_prune_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    return call_unity_maintenance_prune_tool_base(
        arguments,
        ensure_project_root=ensure_project_root,
        prune_project_artifacts=prune_project_artifacts,
        bridge_root=bridge_root,
        request_journal_dir=request_journal_dir,
        scenario_results_dir=scenario_results_dir,
        active_scenario_run_path=active_scenario_run_path,
        captures_dir=captures_dir,
        logs_dir=logs_dir,
        default_editor_log_path=default_editor_log_path,
        read_json=read_json,
    )


def _optional_string_arg(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise JsonRpcError(-32602, f"{name} must be a string when provided.")
    return value


def _optional_string_list_arg(arguments: dict[str, Any], name: str) -> list[str]:
    value = arguments.get(name)
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise JsonRpcError(-32602, f"{name} must be an array of strings when provided.")
    return list(value)


def _optional_bool_arg(arguments: dict[str, Any], name: str, default: bool) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise JsonRpcError(-32602, f"{name} must be a boolean when provided.")
    return value


def call_xuunity_setup_plan_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    include_test_framework = _optional_string_arg(arguments, "includeTestFramework") or "auto"
    if include_test_framework not in {"auto", "yes", "no"}:
        raise JsonRpcError(-32602, "includeTestFramework must be one of: auto, yes, no.")

    package_source = _optional_string_arg(arguments, "packageSource") or "git"
    if package_source not in {"git", "file"}:
        raise JsonRpcError(-32602, "packageSource must be one of: git, file.")

    try:
        payload = build_setup_plan(
            workspace_root=_optional_string_arg(arguments, "workspaceRoot") or None,
            project_roots=_optional_string_list_arg(arguments, "projectRoots"),
            recursive=_optional_bool_arg(arguments, "recursive", False),
            include_test_framework=include_test_framework,
            package_source=package_source,
            package_version=_optional_string_arg(arguments, "packageVersion") or default_light_mcp_package_version(),
            local_package_source=_optional_string_arg(arguments, "localPackageSource") or str(default_local_package_source()),
        )
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return mcp_json_result(payload)


def call_xuunity_setup_apply_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    plan = arguments.get("plan")
    if not isinstance(plan, dict):
        raise JsonRpcError(-32602, "plan must be an object.")
    approve = _optional_bool_arg(arguments, "approve", False)
    project_roots = _optional_string_list_arg(arguments, "projectRoots")
    try:
        payload = apply_setup_plan(plan, approve=approve, selected_project_roots=project_roots)
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return mcp_json_result(payload)


def call_xuunity_uninstall_plan_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    mode = _optional_string_arg(arguments, "mode") or "project-only-cleanup"
    client = _optional_string_arg(arguments, "client") or "auto"
    try:
        payload = build_uninstall_plan(
            mode=mode,
            project_roots=_optional_string_list_arg(arguments, "projectRoots"),
            workspace_root=_optional_string_arg(arguments, "workspaceRoot") or None,
            recursive=_optional_bool_arg(arguments, "recursive", False),
            client=client,
            include_other_client_helpers=_optional_bool_arg(arguments, "includeOtherClientHelpers", False),
        )
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return mcp_json_result(payload)


def call_xuunity_uninstall_apply_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    plan = arguments.get("plan")
    if not isinstance(plan, dict):
        raise JsonRpcError(-32602, "plan must be an object.")
    approve = _optional_bool_arg(arguments, "approve", False)
    try:
        payload = apply_uninstall_plan(plan, approve=approve)
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return mcp_json_result(payload)


def call_xuunity_setup_validate_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")
    try:
        project_root = normalize_setup_project_root(project_root_value)
        payload = validate_setup(
            project_root,
            include_tests=_optional_bool_arg(arguments, "includeTests", False),
        )
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return mcp_json_result(payload, is_error=payload.get("validation_status") == "blocked")


def call_unity_license_capabilities_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")
    timeout_ms = arguments.get("timeoutMs", 30000)
    if not isinstance(timeout_ms, int):
        raise JsonRpcError(-32602, "timeoutMs must be an integer.")
    refresh = _optional_bool_arg(arguments, "refresh", False)
    unity_app_value = _optional_string_arg(arguments, "unityApp") or None
    try:
        project_root = ensure_project_root(project_root_value)
        unity_app = detect_unity_app_path_for_project(project_root, unity_app_value)
        payload = build_license_capabilities(
            project_root=project_root,
            unity_app=unity_app,
            refresh=refresh,
            timeout_ms=timeout_ms,
        )
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return mcp_json_result(payload)


def call_unity_project_action_list_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")

    catalog_path = _optional_string_arg(arguments, "catalogPath")
    try:
        project_root = ensure_project_root(project_root_value)
        catalog = load_project_action_catalog(project_root, catalog_path)
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return mcp_json_result(project_action_catalog_payload(catalog))


def call_unity_project_action_invoke_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")

    action_id = arguments.get("actionId")
    if not isinstance(action_id, str) or not action_id.strip():
        raise JsonRpcError(-32602, "actionId is required.")

    payload = arguments.get("payload", {})
    if not isinstance(payload, dict):
        raise JsonRpcError(-32602, "payload must be an object when provided.")

    wait_for_result = _optional_bool_arg(arguments, "waitForResult", True)
    allow_mutating = _optional_bool_arg(arguments, "allowMutating", False)
    poll_interval_ms = arguments.get("pollIntervalMs", 1000)
    if not isinstance(poll_interval_ms, int):
        raise JsonRpcError(-32602, "pollIntervalMs must be an integer.")

    try:
        project_root = ensure_project_root(project_root_value)
        timeout_ms = resolve_operation_timeout_ms(
            project_root,
            "unity.scenario.run",
            arguments.get("timeoutMs"),
            600000,
        )
        result, is_error = invoke_project_action_from_catalog(
            project_root=project_root,
            requested_action=action_id,
            action_payload=dict(payload),
            catalog_path=_optional_string_arg(arguments, "catalogPath"),
            scenario_name=_optional_string_arg(arguments, "scenarioName"),
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
            wait_for_result=wait_for_result,
            allow_mutating=allow_mutating,
        )
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return mcp_json_result(result, is_error=is_error)


def call_unity_artifact_register_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")

    path_value = arguments.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise JsonRpcError(-32602, "path is required.")

    metadata = arguments.get("metadata", {})
    if not isinstance(metadata, dict):
        raise JsonRpcError(-32602, "metadata must be an object when provided.")

    try:
        project_root = ensure_project_root(project_root_value)
        payload = register_artifact(
            project_root=project_root,
            artifact_path=path_value,
            destination=_optional_string_arg(arguments, "destination") or "repo_artifact",
            kind=_optional_string_arg(arguments, "kind") or "artifact",
            producer=_optional_string_arg(arguments, "producer") or "",
            artifact_schema_version=_optional_string_arg(arguments, "artifactSchemaVersion") or "",
            language=_optional_string_arg(arguments, "language") or "",
            retention_policy=_optional_string_arg(arguments, "retentionPolicy") or "project",
            metadata=dict(metadata),
            workspace_root=_optional_string_arg(arguments, "workspaceRoot") or "",
            allow_unity_assets=_optional_bool_arg(arguments, "allowUnityAssets", False),
        )
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return mcp_json_result(payload)


def call_unity_artifact_write_report_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")

    content = arguments.get("content")
    if not isinstance(content, str):
        raise JsonRpcError(-32602, "content is required and must be a string.")

    metadata = arguments.get("metadata", {})
    if not isinstance(metadata, dict):
        raise JsonRpcError(-32602, "metadata must be an object when provided.")

    try:
        project_root = ensure_project_root(project_root_value)
        payload = write_artifact_report(
            project_root=project_root,
            content=content,
            destination=_optional_string_arg(arguments, "destination") or "repo_report",
            category=_optional_string_arg(arguments, "category") or "XUUnityLightUnityMcp",
            relative_path=_optional_string_arg(arguments, "relativePath") or "",
            kind=_optional_string_arg(arguments, "kind") or "report",
            producer=_optional_string_arg(arguments, "producer") or "",
            artifact_schema_version=_optional_string_arg(arguments, "artifactSchemaVersion") or "",
            language=_optional_string_arg(arguments, "language") or "",
            retention_policy=_optional_string_arg(arguments, "retentionPolicy") or "project",
            metadata=dict(metadata),
            workspace_root=_optional_string_arg(arguments, "workspaceRoot") or "",
            allow_unity_assets=_optional_bool_arg(arguments, "allowUnityAssets", False),
        )
    except ToolInvocationError as exc:
        return mcp_json_result(build_tool_error_payload(exc), is_error=True)
    return mcp_json_result(payload)


def invoke_project_action_from_catalog(
    *,
    project_root: Path,
    requested_action: str,
    action_payload: dict[str, Any],
    catalog_path: str,
    scenario_name: str,
    timeout_ms: int,
    poll_interval_ms: int,
    wait_for_result: bool,
    allow_mutating: bool,
) -> tuple[dict[str, Any], bool]:
    catalog = load_project_action_catalog(project_root, catalog_path)
    action_record = resolve_project_action(catalog, requested_action)
    if bool(action_record.get("mutation")) and not allow_mutating:
        raise ToolInvocationError(
            "project_action_mutation_approval_required",
            (
                f"Project action '{action_record.get('action_id')}' declares mutations. "
                "Pass allowMutating=true only after reviewing the action catalog contract."
            ),
            {
                "action_id": str(action_record.get("action_id") or ""),
                "mutates": list(action_record.get("mutates") or []),
                "catalog_path": str(catalog.get("catalog_path") or ""),
            },
        )

    scenario = build_project_action_scenario(
        action_record=action_record,
        action_payload=action_payload,
        scenario_name=scenario_name,
    )
    run_response = invoke_bridge(
        str(project_root),
        "unity.scenario.run",
        {"scenario": scenario},
        max(5000, min(timeout_ms, 15000)),
    )
    run_tool_result = bridge_response_to_tool_result(run_response)
    if run_tool_result.get("isError"):
        return dict(run_tool_result.get("structuredContent") or {}), True

    run_payload = run_tool_result.get("structuredContent") or {}
    if not isinstance(run_payload, dict):
        run_payload = {}

    scenario_summary = None
    if wait_for_result:
        run_id = str(run_payload.get("run_id") or "")
        effective_scenario_name = str(run_payload.get("scenario_name") or scenario.get("name") or "")
        result_payload = wait_for_scenario_result(
            project_root=project_root,
            run_id=run_id,
            scenario_name=effective_scenario_name,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
        )
        scenario_summary = build_scenario_result_summary_from_context(
            project_root,
            result_payload if isinstance(result_payload, dict) else {},
        )

    result = build_project_action_invocation_payload(
        project_root=project_root,
        catalog=catalog,
        action_record=action_record,
        requested_action=requested_action,
        action_payload=action_payload,
        scenario=scenario,
        run_payload=run_payload,
        scenario_summary=scenario_summary,
        wait_for_result=wait_for_result,
    )
    return result, wait_for_result and not bool(result.get("succeeded"))


def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    return call_tool_base(
        name,
        arguments,
        tools=TOOLS,
        special_tool_handlers={
            "xuunity_setup_plan": call_xuunity_setup_plan_tool,
            "xuunity_setup_apply": call_xuunity_setup_apply_tool,
            "xuunity_uninstall_plan": call_xuunity_uninstall_plan_tool,
            "xuunity_uninstall_apply": call_xuunity_uninstall_apply_tool,
            "xuunity_setup_validate": call_xuunity_setup_validate_tool,
            "unity_license_capabilities": call_unity_license_capabilities_tool,
            "unity_status_summary": call_unity_status_summary_tool,
            "unity_request_final_status": call_unity_request_final_status_tool,
            "unity_scenario_result_summary": call_unity_scenario_result_summary_tool,
            "unity_scenario_results_list": call_unity_scenario_results_list_tool,
            "unity_scenario_result_latest": call_unity_scenario_result_latest_tool,
            "unity_maintenance_prune": call_unity_maintenance_prune_tool,
            "unity_compile_build_config_matrix": call_unity_compile_build_config_matrix_tool,
            "unity_scenario_validate": call_unity_scenario_validate_tool,
            "unity_scenario_run": call_unity_scenario_run_tool,
            "unity_scenario_run_and_wait": call_unity_scenario_run_and_wait_tool,
            "unity_loading_timing": call_unity_loading_timing_tool,
            "unity_project_action_list": call_unity_project_action_list_tool,
            "unity_project_action_invoke": call_unity_project_action_invoke_tool,
            "unity_artifact_register": call_unity_artifact_register_tool,
            "unity_artifact_write_report": call_unity_artifact_write_report_tool,
        },
        tool_invocation_error_type=ToolInvocationError,
        ensure_project_root=ensure_project_root,
        resolve_operation_timeout_ms=resolve_operation_timeout_ms,
        invoke_bridge=invoke_bridge,
        build_tool_error_payload=build_tool_error_payload,
        bridge_response_to_tool_result=bridge_response_to_tool_result,
    )


def build_initialize_result(requested_version: str | None) -> dict[str, Any]:
    return build_initialize_result_base(
        requested_version,
        protocol_version=PROTOCOL_VERSION,
        server_info=SERVER_INFO,
    )


def list_tools_result() -> dict[str, Any]:
    return list_tools_result_base(TOOLS)


def handle_json_rpc_message(message: dict[str, Any], session: dict[str, Any]) -> dict[str, Any] | None:
    return handle_json_rpc_message_base(
        message,
        session,
        protocol_version=PROTOCOL_VERSION,
        server_info=SERVER_INFO,
        tools=TOOLS,
        call_tool=call_tool,
    )


def serve_stdio() -> int:
    return serve_stdio_base(
        protocol_version=PROTOCOL_VERSION,
        handle_message=handle_json_rpc_message,
    )




# === Block C: Batch Execution Engine ===
def load_batch_side_effect_allow_config(path_value: str | None) -> dict[str, Any]:
    return load_side_effect_allow_file(path_value or "", tool_error_type=ToolInvocationError)


def progress_stdout_enabled(args: Any) -> bool:
    return not bool(getattr(args, "no_progress_stdout", False))


def normalize_batch_fallback_mode(value: Any) -> str:
    mode = str(value or "auto").strip()
    if mode not in {"auto", "off", "require-batch"}:
        raise ToolInvocationError(
            "invalid_batch_fallback_mode",
            "--batch-fallback-mode must be one of: auto, off, require-batch.",
        )
    return mode


def batch_start_editor_state(project_root: Path) -> dict[str, Any]:
    visibility = process_visibility_summary()
    process_visibility_available = bool(visibility.get("process_visibility_available"))
    live_project_editor_pids = list_live_project_editor_pids(project_root) if process_visibility_available else []
    bridge_state = try_read_live_editor_state(project_root)
    if not bridge_state:
        try:
            bridge_state = current_project_context_bridge_state(project_root)
        except ToolInvocationError:
            bridge_state = {}
    return {
        "process_visibility_available": process_visibility_available,
        "process_visibility_error_code": str(visibility.get("process_visibility_error_code") or ""),
        "live_project_editor_pids": live_project_editor_pids,
        "same_project_editor_closed": process_visibility_available and not live_project_editor_pids,
        "bridge_state_present": bool(bridge_state),
        "bridge_editor_pid": int((bridge_state or {}).get("editor_pid") or 0),
        "health_status": str((bridge_state or {}).get("health_status") or ""),
        "playmode_state": str((bridge_state or {}).get("playmode_state") or ""),
        "is_compiling": bool((bridge_state or {}).get("is_compiling")),
        "is_updating": bool((bridge_state or {}).get("is_updating")),
        "is_playing": bool((bridge_state or {}).get("is_playing")),
        "is_playing_or_will_change_playmode": bool((bridge_state or {}).get("is_playing_or_will_change_playmode")),
    }


def gui_fallback_busy_reasons(project_root: Path, start_editor_state: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    bridge_state = try_read_live_editor_state(project_root)
    if not bridge_state:
        try:
            bridge_state = current_project_context_bridge_state(project_root)
        except ToolInvocationError:
            bridge_state = {}
    if not bridge_state:
        return ["bridge_state_unavailable"]
    if not bridge_state_is_ready(bridge_state, DEFAULT_HEARTBEAT_MAX_AGE_SECONDS):
        reasons.append("bridge_not_ready")
    if bool(bridge_state.get("is_compiling")):
        reasons.append("is_compiling")
    if bool(bridge_state.get("is_updating")):
        reasons.append("is_updating")
    if bool(bridge_state.get("is_playing")):
        reasons.append("is_playing")
    if bool(bridge_state.get("is_playing_or_will_change_playmode")):
        reasons.append("is_playing_or_will_change_playmode")
    if bool(bridge_state.get("playmode_transition_pending")):
        reasons.append("playmode_transition_pending")
    playmode_state = str(bridge_state.get("playmode_state") or "")
    if playmode_state and playmode_state != "edit":
        reasons.append(f"playmode_state:{playmode_state}")
    return reasons


def attach_license_lane_fields(payload: dict[str, Any], license_capabilities: dict[str, Any] | None) -> None:
    license_capabilities = dict(license_capabilities or {})
    payload["license_capabilities"] = license_capabilities
    payload["license_batchmode_supported"] = license_capabilities.get("batchmode_supported")
    payload["license_blocker_code"] = str(license_capabilities.get("batchmode_blocker_code") or "")
    payload["license_recommended_execution_lane"] = str(license_capabilities.get("recommended_execution_lane") or "")
    payload["batchmode_probe_log_path"] = str(license_capabilities.get("batchmode_probe_log_path") or "")


def attach_batch_lane_fields_to_summary(summary: dict[str, Any], payload: dict[str, Any]) -> None:
    for key in (
        "requested_execution_lane",
        "effective_execution_lane",
        "lane_fallback_reason",
        "batch_fallback_mode",
        "license_batchmode_supported",
        "license_blocker_code",
        "batchmode_probe_log_path",
        "start_editor_state",
        "restore_editor_state",
        "gui_fallback_log_path",
        "next_distinct_action",
    ):
        if key in payload:
            summary[key] = payload[key]


def batch_lane_preflight_blocker(
    *,
    project_root: Path,
    unity_app: Path,
    batch_fallback_mode: str,
    payload: dict[str, Any],
    action_label: str,
    timeout_ms: int | None,
    refresh_license: bool = False,
) -> tuple[str, dict[str, Any] | None]:
    mode = normalize_batch_fallback_mode(batch_fallback_mode)
    payload["requested_execution_lane"] = "batch"
    payload["effective_execution_lane"] = "batch"
    payload["batch_fallback_mode"] = mode
    payload.setdefault("license_batchmode_supported", None)
    payload.setdefault("license_blocker_code", "")
    payload.setdefault("batchmode_probe_log_path", "")

    start_state = batch_start_editor_state(project_root)
    payload["start_editor_state"] = start_state
    if not bool(start_state.get("process_visibility_available")):
        details = {
            "live_editor_pids": [],
            "live_project_editor_pids": [],
            "same_project_editor_closed": False,
            "process_exit_verified": False,
            "process_visibility_available": False,
            "process_visibility_error_code": str(start_state.get("process_visibility_error_code") or "process_visibility_restricted"),
            "closeout_classification": "process_visibility_restricted",
            "recommended_next_action": "restore_host_process_visibility",
            "next_distinct_action": "restore_host_process_visibility",
            "closeout_verification_required": True,
            "closeout_verification_note": "Batch lane selection requires host process visibility before launch or GUI fallback.",
            "requested_execution_lane": "batch",
            "effective_execution_lane": "none",
            "batch_fallback_mode": mode,
        }
        raise ToolInvocationError(
            "process_visibility_restricted",
            (
                f"Refusing to start {action_label} because host process visibility is unavailable. "
                "The MCP cannot prove closed-editor batch safety or safe GUI fallback restoration."
            ),
            details,
        )

    live_editor_pids = list(start_state.get("live_project_editor_pids") or [])
    if live_editor_pids:
        if mode == "auto":
            payload["effective_execution_lane"] = "gui"
            payload["lane_fallback_reason"] = "editor_running_batch_conflict"
            return "gui", None
        raise ToolInvocationError(
            "editor_running_batch_conflict",
            (
                f"Refusing to start {action_label} while the Unity project is open in the editor. "
                f"Live editor pid(s): {', '.join(str(pid) for pid in live_editor_pids)}. "
                "Close the same project editor instance first or use the interactive MCP lane."
            ),
            {
                **build_batch_editor_conflict_details(project_root, live_editor_pids),
                "requested_execution_lane": "batch",
                "effective_execution_lane": "none",
                "batch_fallback_mode": mode,
            },
        )

    license_capabilities = build_license_capabilities(
        project_root=project_root,
        unity_app=unity_app,
        refresh=refresh_license,
        timeout_ms=timeout_ms or 30000,
    )
    attach_license_lane_fields(payload, license_capabilities)
    batchmode_supported = license_capabilities.get("batchmode_supported")
    if mode == "require-batch" and batchmode_supported is not True:
        blocker_code = str(license_capabilities.get("batchmode_blocker_code") or "batchmode_not_proven")
        details = {
            "requested_execution_lane": "batch",
            "effective_execution_lane": "none",
            "batch_fallback_mode": mode,
            "license_batchmode_supported": batchmode_supported,
            "license_blocker_code": blocker_code,
            "batchmode_probe_log_path": str(license_capabilities.get("batchmode_probe_log_path") or ""),
            "license_capabilities": license_capabilities,
            "recommended_next_action": "use_gui_fallback_or_fix_batch_license",
            "next_distinct_action": "rerun_with_batch_fallback_auto_or_restore_batch_license",
        }
        raise ToolInvocationError(
            "batchmode_not_supported",
            f"Unity batchmode support is not proven for this editor/session. blocker={blocker_code}.",
            details,
        )
    if mode == "auto" and batchmode_supported is False:
        if license_capabilities.get("editor_ui_supported") is False:
            details = {
                "requested_execution_lane": "batch",
                "effective_execution_lane": "none",
                "batch_fallback_mode": mode,
                "license_batchmode_supported": False,
                "license_blocker_code": str(license_capabilities.get("batchmode_blocker_code") or ""),
                "batchmode_probe_log_path": str(license_capabilities.get("batchmode_probe_log_path") or ""),
                "license_capabilities": license_capabilities,
                "recommended_next_action": "fix_license_or_use_batch_capable_editor",
                "next_distinct_action": "inspect_license_capabilities",
            }
            raise ToolInvocationError(
                "batchmode_and_gui_unavailable",
                "Unity batchmode is blocked and this license/session does not appear to allow editor UI fallback.",
                details,
            )
        payload["effective_execution_lane"] = "gui"
        payload["lane_fallback_reason"] = str(license_capabilities.get("batchmode_blocker_code") or "batchmode_unavailable")
        return "gui", license_capabilities
    return "batch", license_capabilities


def infer_gui_operation_succeeded(response: dict[str, Any], result_payload: dict[str, Any] | None) -> bool:
    if response.get("status") != "ok":
        return False
    if not isinstance(result_payload, dict):
        return True
    if "succeeded" in result_payload:
        return bool(result_payload.get("succeeded"))
    status = str(result_payload.get("status") or "").strip().lower()
    if status:
        return status in {"passed", "success", "succeeded", "ok"}
    result = result_payload.get("result")
    if isinstance(result, dict):
        result_status = str(result.get("status") or "").strip().lower()
        if result_status:
            return result_status in {"passed", "success", "succeeded", "ok"}
    build_result = str(result_payload.get("build_result") or "").strip().lower()
    if build_result:
        return build_result == "succeeded"
    return True


def run_gui_fallback_operation(
    *,
    project_root: Path,
    unity_app: Path,
    payload: dict[str, Any],
    action_label: str,
    operation: str,
    operation_args: dict[str, Any],
    timeout_ms: int | None,
    log_path: Path,
    result_path: Path,
    summary_path: Path,
    workspace_root: Path | None = None,
    side_effect_mode: str = "git",
    side_effect_allow_config: dict[str, Any] | None = None,
    artifact_probe_config: dict[str, Any] | None = None,
    artifact_probe_path_override: str = "",
    artifact_probe_warn_only: bool = False,
) -> None:
    start_state = dict(payload.get("start_editor_state") or batch_start_editor_state(project_root))
    payload["start_editor_state"] = start_state
    payload["requested_execution_lane"] = "batch"
    payload["effective_execution_lane"] = "gui"
    payload["gui_operation"] = operation
    payload["gui_operation_args"] = operation_args
    payload["gui_fallback_log_path"] = str(log_path)
    payload["next_distinct_action"] = "inspect_gui_fallback_summary"

    live_editor_pids = list(start_state.get("live_project_editor_pids") or [])
    opened_by_fallback = not live_editor_pids
    if live_editor_pids:
        busy_reasons = gui_fallback_busy_reasons(project_root, start_state)
        if busy_reasons:
            details = dict(payload)
            details["gui_fallback_busy_reasons"] = busy_reasons
            details["recommended_next_action"] = "wait_for_editor_idle_or_exit_playmode"
            details["next_distinct_action"] = "return_editor_to_idle_edit_mode_then_retry"
            raise ToolInvocationError(
                "gui_fallback_editor_busy",
                (
                    "Batch lane selected GUI fallback because batch is unavailable or conflicting, "
                    f"but the currently open editor is not safely idle: {', '.join(busy_reasons)}."
                ),
                details,
            )
    else:
        try:
            launch = open_unity_editor(project_root, log_path, unity_app, True)
            ready_state = wait_for_ready(
                project_root=project_root,
                timeout_ms=timeout_ms or 300000,
                heartbeat_max_age_seconds=DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
                startup_policy="fail_fast_on_interactive_compile_block",
                editor_log_path=log_path,
            )
            if not bool((launch or {}).get("reused_existing_editor")):
                update_host_editor_session_pid(project_root, int(ready_state.get("editor_pid") or 0))
            refresh_project_context(project_root)
            payload["gui_fallback_launch"] = launch
            payload["gui_fallback_ready_state"] = ready_state
        except Exception:
            payload["restore_editor_state"] = restore_host_opened_editor_state(project_root, 30000, request_editor_quit)
            raise

    effective_workspace_root = (workspace_root or project_root).expanduser().resolve()
    before_side_effect_mode = "unavailable"
    before_dirty_paths: list[str] = []
    if side_effect_mode != "off":
        before_side_effect_mode, before_dirty_paths = capture_git_dirty_paths(effective_workspace_root)

    result_payload: dict[str, Any] | None = None
    response: dict[str, Any] = {}
    restore_state: dict[str, Any] = {}
    try:
        response = invoke_bridge(
            str(project_root),
            operation,
            operation_args,
            resolve_operation_default_timeout_ms(project_root, operation, timeout_ms or 300000) if timeout_ms is None else timeout_ms,
        )
        result_payload = _decode_bridge_payload_dict(response)
        if isinstance(result_payload, dict):
            result_payload.setdefault("operation", operation)
            result_payload.setdefault("validation_evidence", "unity_gui")
            result_path.parent.mkdir(parents=True, exist_ok=True)
            write_json(result_path, result_payload)
    finally:
        if opened_by_fallback:
            restore_state = restore_host_opened_editor_state(project_root, 30000, request_editor_quit)
            payload["restore_editor_state"] = restore_state
            if not bool(restore_state.get("same_project_editor_closed")):
                payload["next_distinct_action"] = "manual_editor_close_or_terminate_then_verify_closed"
        else:
            payload["restore_editor_state"] = {
                "project_root": str(project_root),
                "restored": False,
                "reason": "editor_was_already_open_before_gui_fallback",
                "same_project_editor_closed": False,
                "process_exit_verified": False,
                "closeout_classification": "left_open_initial_editor",
                "recommended_next_action": "none",
            }

    if side_effect_mode == "off":
        side_effects = unavailable_workspace_side_effects(effective_workspace_root, mode="off")
    else:
        after_side_effect_mode, after_dirty_paths = capture_git_dirty_paths(effective_workspace_root)
        effective_side_effect_mode = "git" if before_side_effect_mode == "git" and after_side_effect_mode == "git" else "unavailable"
        side_effects = (
            build_workspace_side_effects(
                workspace_root=effective_workspace_root,
                before_dirty_paths=before_dirty_paths,
                after_dirty_paths=after_dirty_paths,
                mode=effective_side_effect_mode,
                allow_config=side_effect_allow_config,
            )
            if effective_side_effect_mode == "git"
            else unavailable_workspace_side_effects(effective_workspace_root)
        )
    payload["workspace_side_effects"] = side_effects

    succeeded = infer_gui_operation_succeeded(response, result_payload)
    artifact_probe_summary = None
    artifact_probe_succeeded = True
    if artifact_probe_config is not None:
        artifact_probe_summary = run_artifact_probe(
            artifact_probe_config,
            artifact_path_override=artifact_probe_path_override,
            truncate_text=truncate_text,
        )
        artifact_probe_succeeded = bool(artifact_probe_summary.get("succeeded"))
        payload["artifact_probe_summary"] = artifact_probe_summary
        payload["artifact_probe_succeeded"] = artifact_probe_succeeded
        succeeded = succeeded and (artifact_probe_succeeded or artifact_probe_warn_only)

    payload["bridge_response"] = response
    payload["result_payload_present"] = result_payload is not None
    if str(payload.get("action") or "") == "plain_batch_build":
        payload["build_result_payload_present"] = result_payload is not None
        payload["build_succeeded"] = infer_gui_operation_succeeded(response, result_payload)
    payload["result_file"] = str(result_path)
    payload["succeeded"] = bool(succeeded)
    result_summary = build_batch_execution_summary(
        action=str(payload.get("action") or action_label),
        result_payload=result_payload,
        batch_exit_code=0 if response.get("status") == "ok" else 1,
        succeeded=bool(succeeded),
        result_path=result_path,
        log_path=log_path,
        log_excerpt_hint="",
        truncate_text=truncate_text,
    )
    result_summary["transport_outcome"] = "gui_operation_completed" if response.get("status") == "ok" else "gui_operation_failed"
    result_summary["effective_execution_lane"] = "gui"
    result_summary["workspace_side_effects"] = side_effects
    if "build_succeeded" in payload:
        result_summary["build_succeeded"] = payload["build_succeeded"]
    if str(payload.get("action") or "") == "plain_batch_build":
        result_summary["artifact_probe_succeeded"] = artifact_probe_succeeded
    if artifact_probe_summary is not None:
        result_summary["artifact_probe_succeeded"] = artifact_probe_succeeded
        result_summary["artifact_probe_summary"] = artifact_probe_summary
    attach_batch_lane_fields_to_summary(result_summary, payload)
    write_batch_summary_artifact(summary_path, result_summary)
    payload["summary_file"] = str(summary_path)
    payload["result_summary"] = result_summary
    if str(payload.get("action") or "") == "plain_batch_build":
        payload["build_result_summary"] = result_summary
    if "top_actionable_error" in result_summary:
        payload["top_actionable_error"] = result_summary["top_actionable_error"]
    if opened_by_fallback and not bool((restore_state or {}).get("same_project_editor_closed")):
        payload["succeeded"] = False
        payload["top_actionable_error"] = "GUI fallback completed but editor closeout was not verified."

    print_json(payload)
    if not bool(payload.get("succeeded")):
        raise SystemExit(1)


def ensure_batch_project_closed(project_root: Path, action_label: str):
    visibility = process_visibility_summary()
    if not bool(visibility.get("process_visibility_available")):
        details = {
            "live_editor_pids": [],
            "live_project_editor_pids": [],
            "same_project_editor_closed": False,
            "process_exit_verified": False,
            "closeout_classification": "process_visibility_restricted",
            "recommended_next_action": "restore_host_process_visibility",
            "next_distinct_action": "restore_host_process_visibility",
            "closeout_verification_required": True,
            "closeout_verification_note": "Closed-editor batch lanes require host process visibility before launch.",
        }
        details.update(visibility)
        raise ToolInvocationError(
            "process_visibility_restricted",
            (
                f"Refusing to start {action_label} because host process visibility is unavailable. "
                "The closed-project batch lane cannot prove that this Unity project editor is closed."
            ),
            details,
        )
    live_editor_pids = list_live_project_editor_pids(project_root)
    if live_editor_pids:
        raise ToolInvocationError(
            "editor_running_batch_conflict",
            (
                f"Refusing to start {action_label} while the Unity project is open in the editor. "
                f"Live editor pid(s): {', '.join(str(pid) for pid in live_editor_pids)}. "
                "Close the same project editor instance first or use the interactive MCP lane."
            ),
            build_batch_editor_conflict_details(project_root, live_editor_pids),
        )


def run_batch_operation(
    *,
    project_root: Path,
    unity_app: Path,
    command: list[str],
    payload: dict[str, Any],
    log_path: Path,
    result_path: Path,
    dry_run: bool,
    timeout_ms: int | None = None,
    workspace_root: Path | None = None,
    side_effect_mode: str = "git",
    side_effect_allow_config: dict[str, Any] | None = None,
    progress_interval_seconds: float = DEFAULT_BATCH_PROGRESS_INTERVAL_SECONDS,
    progress_stdout: bool = True,
    batch_fallback_mode: str = "auto",
    refresh_license: bool = False,
    gui_operation: str = "",
    gui_operation_args: dict[str, Any] | None = None,
    artifact_probe_config: dict[str, Any] | None = None,
    artifact_probe_path_override: str = "",
    artifact_probe_warn_only: bool = False,
    last_known_output_path: str = "",
):
    if timeout_ms is not None and timeout_ms <= 0:
        timeout_ms = None
    payload["timeout_ms"] = timeout_ms
    payload["requested_execution_lane"] = "batch"
    payload["effective_execution_lane"] = "batch"
    payload["batch_fallback_mode"] = normalize_batch_fallback_mode(batch_fallback_mode)

    if dry_run:
        print_json(payload)
        return

    summary_path = batch_summary_artifact_path(result_path)
    payload["summary_file"] = str(summary_path)
    run_id = build_batch_run_id(
        str(payload.get("action") or "batch_operation"),
        str(payload.get("build_target") or payload.get("compile_name") or payload.get("name") or ""),
    )
    progress_path = batch_progress_sidecar_path(project_root, run_id)
    progress_reporter = BatchProgressReporter(
        run_id=run_id,
        operation=str(payload.get("action") or "batch operation"),
        log_path=log_path,
        progress_path=progress_path,
        interval_seconds=progress_interval_seconds,
        stdout=progress_stdout,
    )
    payload["run_id"] = run_id
    payload["progress_file"] = str(progress_path)
    progress_reporter.emit("preflight")

    try:
        progress_reporter.emit("prepare_started")
        selected_lane, _license_capabilities = batch_lane_preflight_blocker(
            project_root=project_root,
            unity_app=unity_app,
            batch_fallback_mode=batch_fallback_mode,
            payload=payload,
            action_label=str(payload.get("action") or "batch operation"),
            timeout_ms=timeout_ms,
            refresh_license=refresh_license,
        )
        if selected_lane == "gui":
            if not gui_operation:
                raise ToolInvocationError(
                    "gui_fallback_not_available",
                    f"{payload.get('action') or 'batch operation'} does not provide a GUI fallback operation.",
                    {
                        "requested_execution_lane": "batch",
                        "effective_execution_lane": "none",
                        "batch_fallback_mode": batch_fallback_mode,
                        "lane_fallback_reason": str(payload.get("lane_fallback_reason") or ""),
                        "recommended_next_action": "use_batch_fallback_off_or_fix_batchmode",
                        "next_distinct_action": "inspect_license_capabilities",
                    },
                )
            progress_reporter.emit("prepare_completed", message="Batch preflight selected GUI fallback.")
            run_gui_fallback_operation(
                project_root=project_root,
                unity_app=unity_app,
                payload=payload,
                action_label=str(payload.get("action") or "batch operation"),
                operation=gui_operation,
                operation_args=dict(gui_operation_args or {}),
                timeout_ms=timeout_ms,
                log_path=log_path,
                result_path=result_path,
                summary_path=summary_path,
                workspace_root=workspace_root,
                side_effect_mode=side_effect_mode,
                side_effect_allow_config=side_effect_allow_config,
                artifact_probe_config=artifact_probe_config,
                artifact_probe_path_override=artifact_probe_path_override,
                artifact_probe_warn_only=artifact_probe_warn_only,
            )
            return
    except ToolInvocationError as exc:
        summary = build_batch_prepare_failure_summary(
            action=str(payload.get("action") or "batch operation"),
            result_path=result_path,
            log_path=log_path,
            exc=exc,
            truncate_text=truncate_text,
        )
        attach_batch_lane_fields_to_summary(summary, payload)
        write_batch_summary_artifact(summary_path, summary)
        raise attach_batch_summary_to_error(
            exc,
            summary_path=summary_path,
            summary=summary,
            tool_invocation_error_type=ToolInvocationError,
        )

    progress_reporter.emit("prepare_completed")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    payload["stale_lock"] = clear_stale_project_lock(project_root)

    effective_workspace_root = (workspace_root or project_root).expanduser().resolve()
    side_effect_mode = str(side_effect_mode or "git")
    before_side_effect_mode = "unavailable"
    before_dirty_paths: list[str] = []
    if side_effect_mode != "off":
        before_side_effect_mode, before_dirty_paths = capture_git_dirty_paths(effective_workspace_root)

    command_started_at = time.time()
    batch_exit_code, timed_out = run_subprocess_with_progress(
        command,
        reporter=progress_reporter,
        timeout_ms=timeout_ms,
        last_known_output_path=last_known_output_path,
    )

    payload["batch_exit_code"] = batch_exit_code
    payload["timed_out"] = timed_out
    if side_effect_mode == "off":
        side_effects = unavailable_workspace_side_effects(effective_workspace_root, mode="off")
    else:
        after_side_effect_mode, after_dirty_paths = capture_git_dirty_paths(effective_workspace_root)
        effective_side_effect_mode = "git" if before_side_effect_mode == "git" and after_side_effect_mode == "git" else "unavailable"
        side_effects = (
            build_workspace_side_effects(
                workspace_root=effective_workspace_root,
                before_dirty_paths=before_dirty_paths,
                after_dirty_paths=after_dirty_paths,
                mode=effective_side_effect_mode,
                allow_config=side_effect_allow_config,
            )
            if effective_side_effect_mode == "git"
            else unavailable_workspace_side_effects(effective_workspace_root)
        )
    payload["workspace_side_effects"] = side_effects
    progress_reporter.emit("side_effect_scan_completed")

    result_payload = try_read_json_dict(result_path, read_json)
    payload["result_payload_present"] = result_payload is not None
    base_operation_succeeded = (
        bool(result_payload.get("succeeded", False)) and batch_exit_code == 0 and not timed_out
        if result_payload is not None
        else batch_exit_code == 0 and not timed_out
    )
    payload["succeeded"] = base_operation_succeeded
    if str(payload.get("action") or "") == "plain_batch_build":
        payload["build_result_payload_present"] = result_payload is not None
        payload["build_succeeded"] = base_operation_succeeded

    artifact_probe_summary = None
    artifact_probe_succeeded = True
    if artifact_probe_config is not None:
        progress_reporter.emit("artifact_probe_started", last_known_output_path=artifact_probe_path_override)
        artifact_probe_summary = run_artifact_probe(
            artifact_probe_config,
            artifact_path_override=artifact_probe_path_override,
            truncate_text=truncate_text,
        )
        artifact_probe_succeeded = bool(artifact_probe_summary.get("succeeded"))
        payload["artifact_probe_summary"] = artifact_probe_summary
        payload["artifact_probe_succeeded"] = artifact_probe_succeeded
        payload["succeeded"] = bool(payload.get("succeeded")) and (artifact_probe_succeeded or artifact_probe_warn_only)
        progress_reporter.emit("artifact_probe_completed", last_known_output_path=artifact_probe_path_override)

    log_excerpt_hint = ""
    if batch_exit_code != 0 or not bool(payload.get("succeeded")):
        log_excerpt = read_recent_editor_log(log_path, command_started_at)
        if log_excerpt:
            log_excerpt_hint = truncate_text(log_excerpt[-600:], 600)

    result_summary = build_batch_execution_summary(
        action=str(payload.get("action") or "batch operation"),
        result_payload=result_payload,
        batch_exit_code=batch_exit_code,
        succeeded=bool(payload.get("succeeded")),
        result_path=result_path,
        log_path=log_path,
        log_excerpt_hint=log_excerpt_hint,
        truncate_text=truncate_text,
    )
    if timed_out:
        result_summary["timed_out"] = True
        result_summary["timeout_ms"] = timeout_ms
        result_summary.setdefault(
            "top_actionable_error",
            f"Unity batch operation timed out after {timeout_ms} ms.",
        )
    if artifact_probe_summary is not None:
        result_summary["artifact_probe_succeeded"] = artifact_probe_succeeded
        result_summary["artifact_probe_summary"] = artifact_probe_summary
        if not artifact_probe_succeeded:
            failures = artifact_probe_summary.get("failures")
            if isinstance(failures, list) and failures:
                first_failure = failures[0] if isinstance(failures[0], dict) else {}
                result_summary.setdefault(
                    "top_actionable_error",
                    truncate_text(first_failure.get("message") or "Artifact probe failed.", 320),
                )
    if "build_succeeded" in payload:
        result_summary["build_succeeded"] = payload["build_succeeded"]
    result_summary["workspace_side_effects"] = side_effects
    attach_batch_lane_fields_to_summary(result_summary, payload)
    write_batch_summary_artifact(summary_path, result_summary)
    progress_reporter.emit("summary_written")
    payload["result_summary"] = result_summary
    if str(payload.get("action") or "") == "plain_batch_build":
        payload["build_result_summary"] = result_summary
    payload["stale_bridge_state_cleared"] = clear_stale_bridge_state(project_root)
    if "top_actionable_error" in result_summary:
        payload["top_actionable_error"] = result_summary["top_actionable_error"]

    print_json(payload)
    if batch_exit_code != 0 or not bool(payload.get("succeeded")):
        raise SystemExit(1)





# Helper to maintain output formatting
def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False), flush=True)


from server_core import wrap_globals_with_proxies, TimeProxy
wrap_globals_with_proxies(globals(), [
    "activate_unity_editor",
    "build_license_capabilities",
    "build_project_discovery_report",
    "build_request_final_status",
    "clear_stale_bridge_state",
    "current_project_context_bridge_state",
    "current_project_context_discovery_details",
    "current_project_context_host_session_state",
    "derive_busy_reason",
    "detect_unity_app_path_for_project",
    "enrich_tool_invocation_error_with_discovery",
    "ensure_project_root",
    "heartbeat_age_seconds",
    "invoke_bridge",
    "list_live_project_editor_pids",
    "open_unity_editor",
    "pid_is_alive",
    "print_json",
    "process_visibility_summary",
    "read_best_effort_bridge_state",
    "recover_project_bridge_for_reconciliation",
    "refresh_project_context",
    "request_editor_quit",
    "resolve_editor_log_path",
    "resolve_operation_default_timeout_ms",
    "restore_host_opened_editor_state",
    "run_batch_build_config_compile_matrix_probe",
    "run_gui_fallback_operation",
    "run_self_json_command_with_completed",
    "summarize_state_for_error",
    "terminate_editor_pid",
    "try_read_live_editor_state",
    "update_host_editor_session_pid",
    "verify_project_editor_closed",
    "wait_for_ready",
    "wait_for_scenario_result",
    "build_batch_prepare_failure_summary",
    "enrich_error_details_with_discovery",
    "execute_host_health_recovery_policy",
    "ensure_batch_project_closed",
    "batch_lane_preflight_blocker",
    "call_unity_compile_build_config_matrix_tool",
    "call_unity_scenario_run_and_wait_tool",
    "call_unity_scenario_validate_tool",
    "call_unity_loading_timing_tool",
    "call_unity_scenario_run_tool",
    "call_unity_status_summary_tool",
    "call_unity_request_final_status_tool",
    "call_unity_scenario_result_summary_tool",
    "call_unity_scenario_results_list_tool",
    "call_unity_scenario_result_latest_tool",
    "call_unity_maintenance_prune_tool",
    "call_unity_license_capabilities_tool",
    "call_unity_project_action_list_tool",
    "call_unity_project_action_invoke_tool",
    "call_unity_artifact_register_tool",
    "call_unity_artifact_write_report_tool",
])
time = TimeProxy()
