# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import json
import time
from pathlib import Path
from typing import Any

from server_core import ToolInvocationError, read_json, write_json
from server_specs import STARTUP_POLICIES, SCENARIO_TERMINAL_STATUSES
from server_health import FRESH_HEARTBEAT_MAX_AGE_SECONDS

from server_batch_orchestrator import (
    run_batch_operation,
    run_gui_fallback_operation,
    ensure_project_root,
    current_project_context_bridge_state,
    current_project_context_host_session_state,
    current_project_context_discovery_details,
    build_project_discovery_report,
    build_status_summary_from_context,
    run_in_project_request_lock,
    progress_stdout_enabled,
    load_batch_side_effect_allow_config,
    print_json,
    _bridge_error_code,
    apply_discovery_to_final_status_summary,
    bridge_response_to_tool_result,
    build_discovery_scenario_result_summary_for_error,
    build_discovery_status_summary_for_error,
    build_registry_context_report,
    build_request_final_status_from_context,
    build_scenario_result_summary_from_context,
    call_unity_scenario_run_and_wait_tool,
    classify_compile_probe_failure,
    default_light_mcp_package_version,
    default_local_package_source,
    enrich_tool_invocation_error_with_discovery,
    invoke_bridge,
    maybe_fail_fast_offline_ensure_ready_without_open,
    prune_stale_project_contexts,
    recommended_recovery_command_for_project,
    refresh_project_context,
    request_editor_quit,
    run_batch_build_config_compile_matrix_probe,
    run_self_json_command,
    run_self_json_command_with_completed,
    DISCOVERY_STATUS_FALLBACK_ERROR_CODES,
    SCENARIO_RECOVERY_ERROR_CODES,
    invoke_project_action_from_catalog,
)

# Core imports
from server_bridge_runtime import (
    DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
    derive_busy_reason,
    heartbeat_age_seconds,
    pid_is_alive,
    try_read_live_editor_state,
    wait_for_editor_idle,
    active_scenario_run_path,
    annotate_bridge_state_with_liveness,
    bridge_enabled,
    bridge_root,
    bridge_state_path,
    build_bridge_stabilization_summary,
    cancel_request_best_effort,
    captures_dir,
    cleanup_stale_request_artifacts,
    default_editor_log_path,
    logs_dir,
    request_journal_dir,
    scenario_results_dir,
)
from server_editor_host import (
    bridge_state_is_ready,
    clear_stale_bridge_state,
    clear_stale_project_lock,
    default_batch_build_log_path,
    default_batch_build_result_path,
    default_batch_operation_log_path,
    default_batch_operation_result_path,
    detect_unity_app_path_for_project,
    list_live_project_editor_pids,
    open_unity_editor,
    process_visibility_summary,
    read_recent_editor_log,
    resolve_batch_build_output_path,
    restore_host_opened_editor_state,
    update_host_editor_session_pid,
    wait_for_ready,
    build_batch_validation_command,
    build_plain_batch_build_command,
    resolve_editor_log_path,
    verify_project_editor_closed,
)
from server_license import build_license_capabilities
from server_loading_timing import request_loading_timing_summary
from server_summaries import (
    build_scenario_result_summary,
    build_status_summary,
    normalize_scenario_payload,
    prune_project_artifacts,
    truncate_text,
    try_read_json_dict,
)
from server_workspace_effects import (
    build_workspace_side_effects,
    capture_git_dirty_paths,
    load_side_effect_allow_file,
    unavailable_workspace_side_effects,
)

# Scaffold and dependency wizard imports
from server_project_actions import (
    build_project_action_invocation_payload,
    build_project_action_scenario,
    load_project_action_catalog,
    normalize_project_action_scenario,
    project_action_catalog_payload,
    resolve_project_action,
    scaffold_project_hook,
)
from server_project_context import (
    find_repo_local_package_source,
    find_latest_request_event,
    inspect_light_mcp_import_state,
    inspect_package_dependency_alignment,
)
from server_test_reporting import (
    format_test_results,
    select_test_result_rows,
)
from server_setup_wizard import (
    LIGHT_MCP_PACKAGE_NAME,
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
    require_test_framework_capability_for_batch,
)
from server_scenario_results import (
    latest_persisted_scenario_result_summary,
    list_persisted_scenario_result_summaries,
)
from server_operation_evidence import (
    attach_persisted_scenario_result_evidence,
    parse_utc_timestamp,
)
from server_build_config import (
    build_compile_matrix_args_from_build_config,
)
from server_artifact_probe import (
    load_artifact_probe_config,
    run_artifact_probe,
)
from server_artifact_registry import (
    register_artifact,
    write_artifact_report,
    resolve_workspace_root,
)
from server_runtime_config import (
    resolve_operation_default_timeout_ms,
    build_runtime_config_report,
)
from server_batch_reporting import (
    DEFAULT_BATCH_PROGRESS_INTERVAL_SECONDS,
)
import tempfile

from server_setup_regression import (
    TEST_FRAMEWORK_REGRESSION_COMPILE_TARGET,
    TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_TEST_NAME,
    TEST_FRAMEWORK_REGRESSION_LOCK_PACKAGES,
    cleanup_test_framework_regression_focus_fixture,
    compare_candidate_to_baseline,
    deploy_test_framework_regression_focus_fixture,
    normalize_requested_versions,
    read_test_framework_state,
    remove_lock_dependencies,
    run_single_test_framework_candidate,
    test_framework_regression_artifacts_dir,
    test_framework_regression_result_path,
    write_declared_dependency_version,
    write_test_framework_step_artifact,
    summarize_bridge_step,
)


def load_json_file(path_value: str, error_code: str) -> Any:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ToolInvocationError(error_code, f"JSON file not found: {path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolInvocationError(error_code, str(exc)) from exc


def load_optional_json_object(value: str, error_code: str) -> dict[str, Any]:
    if not str(value or "").strip():
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ToolInvocationError(error_code, str(exc)) from exc
    if not isinstance(payload, dict):
        raise ToolInvocationError(error_code, "Expected a JSON object.")
    return payload


def load_project_action_payload_args(args) -> dict[str, Any]:
    payload_json = str(getattr(args, "payload_json", "") or "").strip()
    payload_file = str(getattr(args, "payload_file", "") or "").strip()
    if payload_json and payload_file:
        raise ToolInvocationError(
            "project_action_payload_ambiguous",
            "Use either --payload-json or --payload-file, not both.",
        )
    if payload_json:
        return load_optional_json_object(payload_json, "project_action_payload_invalid")
    if payload_file:
        return load_json_file(payload_file, "project_action_payload_invalid")
    return {}


def load_report_content_args(args) -> str:
    content = str(getattr(args, "content", "") or "")
    content_file = str(getattr(args, "content_file", "") or "").strip()
    if content and content_file:
        raise ToolInvocationError(
            "report_content_ambiguous",
            "Use either --content or --content-file, not both.",
        )
    if content_file:
        path = Path(content_file).expanduser().resolve()
        if not path.is_file():
            raise ToolInvocationError("report_content_file_not_found", f"Content file not found: {path}")
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ToolInvocationError("report_content_file_unreadable", str(exc)) from exc
    return content


__all__ = [name for name in globals() if not name.startswith("__")]
