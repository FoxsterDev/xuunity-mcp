#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

SERVER_INFO = {
    "name": "xuunity-mcp",
    "version": "0.3.33",
}
PROTOCOL_VERSION = "2025-06-18"

# ProcessLauncher configuration
from server_process_launcher import ProcessLauncher
ProcessLauncher.configure(Path(__file__).resolve())

import argparse

# Core types and library imports
from server_core import ToolInvocationError, read_json, write_json
from server_health import FRESH_HEARTBEAT_MAX_AGE_SECONDS, build_editor_log_diagnosis, classify_project_health
from server_batch_reporting import build_batch_prepare_failure_summary
from server_editor_host import (
    classify_editor_log,
    default_editor_log_path,
    find_running_unity_editors_for_project,
    find_running_unity_worker_processes_for_project,
    process_visibility_summary,
    try_read_host_editor_session_state,
    activate_unity_editor,
    clear_stale_bridge_state,
    detect_unity_app_path_for_project,
    open_unity_editor,
    resolve_editor_log_path,
    restore_host_opened_editor_state,
    terminate_editor_pid,
    update_host_editor_session_pid,
    verify_project_editor_closed,
)
from server_bridge_runtime import (
    bridge_enabled,
    bridge_identity_from_state,
    heartbeat_age_seconds,
    inspect_stale_request_artifacts,
    try_read_bridge_state,
    try_read_live_editor_state,
    summarize_state_for_error,
    derive_busy_reason,
    pid_is_alive,
    read_best_effort_bridge_state,
)
from server_discovery import discover_project_context_state
from server_project_context import (
    ensure_project_root as ensure_project_root_base,
    inspect_light_mcp_import_state,
    inspect_package_dependency_alignment,
)
from server_host_platform import current_host_platform_adapter
from server_setup_regression import (
    TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_RELATIVE_DIR,
    TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_TEST_NAME,
    TEST_FRAMEWORK_REGRESSION_LOCK_PACKAGES,
    TEST_FRAMEWORK_REGRESSION_COMPILE_TARGET,
    TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_FILE_NAME,
    TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_SOURCE,
)

# Compatibility re-exports for orchestrator and CLI helpers
from server_batch_orchestrator import (
    MUTATING_BRIDGE_OPERATIONS,
    TProjectOperationResult,
    _bridge_error_code,
    _decode_bridge_payload_dict,
    bridge_operation_requires_request_lock,
    bridge_response_to_tool_result,
    build_registry_context_report,
    build_status_summary_from_context,
    current_project_context_bridge_state,
    current_project_context_discovery_details,
    current_project_context_host_session_state,
    ensure_project_root,
    forget_project_context,
    invoke_bridge,
    list_active_project_contexts,
    prune_project_artifacts,
    prune_stale_project_contexts,
    recommended_recovery_command_for_project,
    recover_project_bridge_for_reconciliation,
    request_editor_quit,
    run_batch_operation,
    run_gui_fallback_operation,
    run_in_project_request_lock,
    serve_stdio,
    wait_for_scenario_result,
    build_tool_error_payload,
    emit_tool_error_summary,
    handle_json_rpc_message,
    ensure_batch_project_closed,
    batch_lane_preflight_blocker,
    call_unity_compile_build_config_matrix_tool,
    call_unity_scenario_run_and_wait_tool,
    call_unity_scenario_validate_tool,
    call_unity_loading_timing_tool,
    call_unity_scenario_run_tool,
    call_unity_status_summary_tool,
    call_unity_request_final_status_tool,
    call_unity_scenario_result_summary_tool,
    call_unity_scenario_results_list_tool,
    call_unity_scenario_result_latest_tool,
    call_unity_maintenance_prune_tool,
    call_unity_license_capabilities_tool,
    call_unity_project_action_list_tool,
    call_unity_project_action_invoke_tool,
    call_unity_artifact_register_tool,
    call_unity_artifact_write_report_tool,
    build_project_discovery_report,
    build_request_final_status,
    enrich_tool_invocation_error_with_discovery,
    wait_for_ready,
    resolve_operation_default_timeout_ms,
    run_batch_build_config_compile_matrix_probe,
    run_self_json_command_with_completed,
    build_status_summary,
    enrich_error_details_with_discovery,
    execute_host_health_recovery_policy,
)

# Registry initialization
from server_registry import initialize_registry

def _build_project_health_details(
    *,
    project_root: Path,
    bridge_state: dict[str, Any],
    host_editor_session_state: dict[str, Any],
    discovery: dict[str, Any],
) -> dict[str, Any]:
    startup_policy = str(
        bridge_state.get("startup_policy")
        or host_editor_session_state.get("startup_policy")
        or "fail_fast_on_interactive_compile_block"
    )
    heartbeat_age = heartbeat_age_seconds(bridge_state) if bridge_state else None
    has_active_editor_context = bool(
        discovery.get("bridge_state_live")
        or discovery.get("host_session_live")
        or int(discovery.get("detected_editor_count") or 0) > 0
        or bool(host_editor_session_state.get("opened_by_host"))
    )
    needs_log_diagnosis = bool(
        has_active_editor_context
        and (
            not discovery.get("bridge_state_live")
            or (
                heartbeat_age is not None
                and heartbeat_age >= FRESH_HEARTBEAT_MAX_AGE_SECONDS
            )
        )
    )
    editor_log_diagnosis = (
        build_editor_log_diagnosis(
            default_editor_log_path(project_root),
            startup_policy=startup_policy,
            classify_editor_log=classify_editor_log,
            session_start_offset_bytes=host_editor_session_state.get("log_session_start_offset_bytes"),
            session_start_mtime=host_editor_session_state.get("log_session_start_mtime"),
        )
        if needs_log_diagnosis
        else {}
    )
    return classify_project_health(
        bridge_state=bridge_state,
        discovery=discovery,
        editor_log_diagnosis=editor_log_diagnosis,
        heartbeat_age_seconds=heartbeat_age_seconds,
        derive_busy_reason=derive_busy_reason,
    )

def _refresh_project_context_state(project_root: Path) -> dict[str, Any]:
    discovery = discover_project_context_state(
        project_root,
        try_read_bridge_state=try_read_bridge_state,
        try_read_host_editor_session_state=try_read_host_editor_session_state,
        find_running_unity_editors_for_project=find_running_unity_editors_for_project,
        find_running_unity_worker_processes_for_project=find_running_unity_worker_processes_for_project,
        pid_is_alive=pid_is_alive,
        bridge_enabled=bridge_enabled,
        build_project_health=_build_project_health_details,
        inspect_package_dependency_alignment=inspect_package_dependency_alignment,
        inspect_stale_request_artifacts=inspect_stale_request_artifacts,
        process_visibility_report=process_visibility_summary,
    )
    bridge_state = dict(discovery.get("last_bridge_state") or {})
    host_editor_session_state = dict(discovery.get("last_host_editor_session_state") or {})
    bridge_generation, bridge_session_id = bridge_identity_from_state(bridge_state)

    return {
        "last_bridge_state": bridge_state,
        "last_host_editor_session_state": host_editor_session_state,
        "active_transport": str(discovery.get("active_transport") or ""),
        "transport_metadata": dict(discovery.get("transport_metadata") or {}),
        "last_seen_pid": int(discovery.get("last_seen_pid") or 0),
        "last_seen_generation": bridge_generation,
        "last_seen_session_id": bridge_session_id,
        "last_refresh_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "last_refresh_unix": time.time(),
        "health_classification": str(
            discovery.get("host_health_classification")
            or bridge_state.get("health_status")
            or discovery.get("discovery_classification")
            or ""
        ),
        "discovery_classification": str(discovery.get("discovery_classification") or ""),
        "discovery_details": discovery,
    }

initialize_registry(ensure_project_root_base, _refresh_project_context_state)
from server_registry import get_registry
_BRIDGE_REGISTRY = get_registry()

# Compatibility re-exports for CLI command handlers
from server_cli_commands import *

# CLI Parser import
from server_cli_parser import build_parser

def main() -> None:
    try:
        if len(sys.argv) == 1:
            raise SystemExit(serve_stdio())

        parser = build_parser()
        args = parser.parse_args()
        if not hasattr(args, "func"):
            parser.print_help()
            raise SystemExit(1)
        args.func(args)
    except ToolInvocationError as exc:
        payload = build_tool_error_payload(exc)
        emit_tool_error_summary(payload)
        # print_json is imported from server_batch_orchestrator
        from server_batch_orchestrator import print_json
        print_json(payload)
        raise SystemExit(1)

if __name__ == "__main__":
    main()
