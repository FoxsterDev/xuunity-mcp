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


def cmd_recover_editor_session(args):
    project_root = ensure_project_root(args.project_root)
    refresh_project_context(project_root)
    initial_discovery = build_project_discovery_report(project_root)

    payload: dict[str, Any] = {
        "action": "recover_editor_session",
        "project_root": str(project_root),
        "dialog_policy": "observe_only",
        "recovery_classification": "inspection_only",
        "initial_discovery": initial_discovery,
        "closeout_attempted": False,
        "compile_probe_attempted": False,
    }

    host_session_state = current_project_context_host_session_state(project_root)
    if bool(host_session_state.get("opened_by_host")):
        payload["closeout_attempted"] = True
        closeout = restore_host_opened_editor_state(project_root, args.close_timeout_ms, request_editor_quit)
        payload["closeout"] = closeout
        refresh_project_context(project_root)
        if not bool(closeout.get("closeout_verified")):
            payload["recovery_classification"] = "closeout_incomplete"
            payload["recovery_recommended_next_action"] = str(
                closeout.get("recommended_next_action")
                or "manual_editor_close"
            )
            payload["recommended_recovery_command"] = str(closeout.get("recommended_recovery_command") or "")
            payload["discovery_after_recovery"] = build_project_discovery_report(project_root)
            print_json(payload)
            raise SystemExit(1)

    refresh_project_context(project_root)
    discovery_after_closeout = build_project_discovery_report(project_root)
    payload["discovery_after_closeout"] = discovery_after_closeout

    detected_editor_pids = list(discovery_after_closeout.get("detected_editor_pids") or [])
    if (
        not detected_editor_pids
        and str(discovery_after_closeout.get("reconciliation_case") or "") in {"stale_bridge_state", "stale_bridge_and_host_session"}
    ):
        payload["stale_bridge_state_cleared"] = clear_stale_bridge_state(project_root)
        refresh_project_context(project_root)
        discovery_after_closeout = build_project_discovery_report(project_root)
        payload["discovery_after_closeout"] = discovery_after_closeout

    diagnosis = dict(discovery_after_closeout.get("editor_log_diagnosis") or {})
    diagnosis_code = str(diagnosis.get("code") or "")
    compile_block_detected = diagnosis_code in {
        "interactive_compile_block_detected",
        "safe_mode_manual_required",
        "package_resolution_failed",
    }

    if compile_block_detected or bool(args.force_compile_probe):
        payload["compile_probe_attempted"] = True
        compile_probe = run_batch_build_config_compile_matrix_probe(
            project_root,
            timeout_ms=args.timeout_ms,
        )
        payload["compile_probe"] = compile_probe
        if not bool(compile_probe.get("succeeded")):
            recovery_classification, next_action, recovery_command_template = classify_compile_probe_failure(compile_probe)
            payload["recovery_classification"] = recovery_classification
            payload["recovery_recommended_next_action"] = next_action
            payload["recommended_recovery_command"] = recovery_command_template.format(project_root=str(project_root))
            if recovery_classification == "compile_red_confirmed":
                payload["reopen_blocked"] = True
                payload["reopen_block_reason"] = "compile_red_after_batch_restore"
            payload["discovery_after_recovery"] = build_project_discovery_report(project_root)
            print_json(payload)
            raise SystemExit(1)

    if args.open_editor:
        ensure_payload, ensure_completed = run_self_json_command_with_completed(
            [
                "ensure-ready",
                "--project-root",
                str(project_root),
                "--open-editor",
                "--timeout-ms",
                str(args.timeout_ms),
                "--heartbeat-max-age-seconds",
                str(args.heartbeat_max_age_seconds),
                "--startup-policy",
                str(args.startup_policy),
            ]
        )
        payload["ensure_ready"] = ensure_payload or {}
        if ensure_completed.returncode != 0:
            payload["recovery_classification"] = "reopen_failed"
            error_payload = dict((ensure_payload or {}).get("error") or {})
            details = dict(error_payload.get("details") or {})
            payload["recovery_recommended_next_action"] = str(
                details.get("recommended_next_action")
                or "inspect_editor_log"
            )
            payload["recommended_recovery_command"] = str(
                details.get("recommended_recovery_command")
                or recommended_recovery_command_for_project(project_root, payload["recovery_recommended_next_action"])
            )
            payload["reopen_error"] = {
                "code": str(error_payload.get("code") or "ensure_ready_failed"),
                "message": str(error_payload.get("message") or truncate_text(ensure_completed.stderr or "", 400)),
                "details": details,
            }
            payload["discovery_after_recovery"] = build_project_discovery_report(project_root)
            print_json(payload)
            raise SystemExit(1)

    payload["recovery_classification"] = "recovered"
    payload["recovery_recommended_next_action"] = "none"
    payload["discovery_after_recovery"] = build_project_discovery_report(project_root)
    print_json(payload)


def cmd_setup_plan(args):
    payload = build_setup_plan(
        workspace_root=args.workspace_root,
        project_roots=list(args.project_root or []),
        recursive=bool(args.recursive),
        include_test_framework=args.include_test_framework,
        package_source=args.package_source,
        package_version=args.package_version or default_light_mcp_package_version(),
        local_package_source=args.local_package_source or str(default_local_package_source()),
    )
    print_json(payload)


def cmd_setup_apply(args):
    plan_path = Path(args.plan_file).expanduser()
    if not plan_path.is_absolute():
        plan_path = (Path.cwd() / plan_path).resolve()
    plan = read_json(plan_path)
    payload = apply_setup_plan(
        plan,
        approve=bool(args.yes),
        selected_project_roots=list(args.project_root or []),
    )
    print_json(payload)


def cmd_uninstall_plan(args):
    payload = build_uninstall_plan(
        mode=args.mode,
        project_roots=list(args.project_root or []),
        workspace_root=args.workspace_root,
        recursive=bool(args.recursive),
        client=args.client,
        include_other_client_helpers=bool(args.include_other_client_helpers),
    )
    print_json(payload)


def cmd_uninstall_apply(args):
    plan_path = Path(args.plan_file).expanduser()
    if not plan_path.is_absolute():
        plan_path = (Path.cwd() / plan_path).resolve()
    plan = read_json(plan_path)
    payload = apply_uninstall_plan(plan, approve=bool(args.yes))
    print_json(payload)


def cmd_validate_setup(args):
    project_root = normalize_setup_project_root(args.project_root)
    payload = validate_setup(project_root, include_tests=bool(args.include_tests))
    print_json(payload)
    if payload.get("validation_status") != "ready":
        raise SystemExit(1)


def cmd_install_test_framework(args):
    project_root = normalize_setup_project_root(args.project_root)
    payload = install_test_framework(project_root, approve=bool(args.yes), version=args.version or "")
    print_json(payload)


def cmd_license_capabilities(args):
    project_root = ensure_project_root(args.project_root)
    unity_app = detect_unity_app_path_for_project(project_root, args.unity_app)
    payload = build_license_capabilities(
        project_root=project_root,
        unity_app=unity_app,
        refresh=bool(args.refresh),
        timeout_ms=int(args.timeout_ms or 30000),
    )
    print_json(payload)


def cmd_request_install_test_framework(args):
    project_root = ensure_project_root(args.project_root)
    response = invoke_bridge(
        str(project_root),
        "unity.package.install_test_framework",
        {
            "approve": bool(args.yes),
            "version": args.version or "",
        },
        resolve_operation_default_timeout_ms(project_root, "unity.package.install_test_framework", 300000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_bridge_state(args):
    project_root = ensure_project_root(args.project_root)
    if not bridge_enabled(project_root):
        raise SystemExit(
            "Bridge is disabled for this project. Enable it with "
            "init_xuunity_light_unity_mcp.sh --project-root <path> --enable-project and reopen Unity."
        )
    state_path = bridge_state_path(project_root)
    if not state_path.is_file():
        raise SystemExit(f"Bridge state file not found: {state_path}")
    print_json(annotate_bridge_state_with_liveness(read_json(state_path)))


def cmd_request_status(args):
    response = invoke_bridge(args.project_root, "unity.status", {}, args.timeout_ms)
    print_json(response)


def cmd_request_status_summary(args):
    project_root = ensure_project_root(args.project_root)
    try:
        response = invoke_bridge(str(project_root), "unity.status", {}, args.timeout_ms)
    except ToolInvocationError as exc:
        if exc.code in DISCOVERY_STATUS_FALLBACK_ERROR_CODES:
            print_json(build_discovery_status_summary_for_error(project_root, exc))
            return
        raise

    tool_result = bridge_response_to_tool_result(response)
    if tool_result.get("isError"):
        print_json(tool_result.get("structuredContent") or {})
        raise SystemExit(1)
    payload = tool_result.get("structuredContent") or {}
    print_json(build_status_summary_from_context(project_root, payload if isinstance(payload, dict) else {}))


def cmd_request_latest_status(args):
    project_root = ensure_project_root(args.project_root)
    operations = [str(operation).strip() for operation in list(args.operation or []) if str(operation).strip()]
    current_state = current_project_context_bridge_state(project_root)
    latest_event = find_latest_request_event(project_root, operations)

    if latest_event is None:
        stabilization = build_bridge_stabilization_summary(current_state)
        print_json(apply_discovery_to_final_status_summary({
            "lookup_mode": "latest_request_by_operation",
            "lookup_found": False,
            "matched_operations": operations,
            "request_id": "",
            "operation": operations[-1] if operations else "",
            "request_started": False,
            "request_completed": False,
            "completion_status": "",
            "operation_outcome": "unknown",
            "reclassified": False,
            "reclassified_status": "",
            "reclassified_reason": "",
            "retryable": False,
            "recommended_next_action": (
                "retry_request" if stabilization["safe_to_retry"] else "wait_for_bridge_stabilization"
            ),
            "request_started_at_utc": "",
            "request_completed_at_utc": "",
            "last_event_type": "",
            "last_event_at_utc": "",
            "last_bridge_generation_seen": int((current_state or {}).get("bridge_generation") or 0),
            "last_bridge_session_id_seen": str((current_state or {}).get("bridge_session_id") or ""),
            "journal_event_count": 0,
            "journal_event_paths": [],
            "bridge_stabilization": stabilization,
        }, project_root))
        return

    request_id = str(latest_event.get("request_id") or "").strip()
    operation = str(latest_event.get("operation") or "").strip()
    summary = build_request_final_status_from_context(project_root, request_id, operation, args.timeout_ms)
    summary["lookup_mode"] = "latest_request_by_operation"
    summary["lookup_found"] = True
    summary["matched_operations"] = operations
    summary["lookup_event_type"] = str(latest_event.get("event_type") or "")
    summary["lookup_event_at_utc"] = str(latest_event.get("event_at_utc") or "")
    summary["lookup_event_path"] = str(latest_event.get("_path") or "")
    print_json(summary)


def cmd_request_final_status(args):
    project_root = ensure_project_root(args.project_root)
    summary = build_request_final_status_from_context(project_root, args.request_id, args.operation or "", args.timeout_ms)
    print_json(summary)


def cmd_request_cancel(args):
    project_root = ensure_project_root(args.project_root)
    print_json(
        cancel_request_best_effort(
            project_root,
            str(args.request_id or ""),
            operation=str(args.operation or ""),
        )
    )


def cmd_request_stale_cleanup(args):
    project_root = ensure_project_root(args.project_root)
    current_state = current_project_context_bridge_state(project_root)
    print_json(
        cleanup_stale_request_artifacts(
            project_root,
            current_state=current_state,
            stale_age_seconds=max(1, int(args.stale_age_seconds or 600)),
            dry_run=bool(args.dry_run),
            max_entries=max(1, int(args.max_entries or 50)),
        )
    )


def cmd_request_playmode_state(args):
    response = invoke_bridge(args.project_root, "unity.playmode.state", {}, args.timeout_ms)
    print_json(response)


def cmd_request_playmode_set(args):
    project_root = ensure_project_root(args.project_root)
    response = invoke_bridge(
        str(project_root),
        "unity.playmode.set",
        {"action": args.action},
        resolve_operation_default_timeout_ms(project_root, "unity.playmode.set", 180000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_capabilities(args):
    response = invoke_bridge(args.project_root, "unity.capabilities.get", {}, args.timeout_ms)
    print_json(response)


def cmd_request_health_probe(args):
    response = invoke_bridge(args.project_root, "unity.health.probe", {}, args.timeout_ms)
    print_json(response)


def cmd_request_build_target_get(args):
    response = invoke_bridge(args.project_root, "unity.build_target.get", {}, args.timeout_ms)
    print_json(response)


def cmd_request_build_target_switch(args):
    response = invoke_bridge(
        args.project_root,
        "unity.build_target.switch",
        {"target": args.target},
        args.timeout_ms,
    )
    print_json(response)


def cmd_request_build_player(args):
    project_root = ensure_project_root(args.project_root)
    build_target = str(args.build_target or "").strip()
    if not build_target:
        raise ToolInvocationError("missing_build_target", "--build-target is required.")
    output_path = resolve_batch_build_output_path(project_root, args.output_path)
    scene_paths = list(args.scene_path or [])
    build_options = list(args.build_option or [])
    result_path = (
        Path(args.result_file).expanduser().resolve()
        if getattr(args, "result_file", "")
        else default_batch_build_result_path(project_root, build_target)
    )
    bridge_args = {
        "buildTarget": build_target,
        "outputPath": output_path,
        "resultFile": str(result_path),
        "scenePaths": scene_paths,
        "buildOptions": build_options,
    }
    response = invoke_bridge(
        str(project_root),
        "unity.build_player",
        bridge_args,
        resolve_operation_default_timeout_ms(project_root, "unity.build_player", 600000) if args.timeout_ms is None else args.timeout_ms,
    )
    payload = {
        "action": "request_build_player",
        "project_root": str(project_root),
        "bridge_response": response,
        "build_target": build_target,
        "output_path": output_path,
        "scene_paths": scene_paths,
        "build_options": build_options,
        "result_file": str(result_path),
    }
    artifact_probe_config = load_artifact_probe_config(
        artifact_probe_file=getattr(args, "artifact_probe_file", "") or "",
        artifact_probe_json=getattr(args, "artifact_probe_json", "") or "",
        tool_error_type=ToolInvocationError,
    )
    if artifact_probe_config is not None:
        summary = run_artifact_probe(
            artifact_probe_config,
            artifact_path_override=output_path,
            truncate_text=truncate_text,
        )
        payload["artifact_probe_summary"] = summary
        payload["artifact_probe_succeeded"] = bool(summary.get("succeeded"))
        if not bool(summary.get("succeeded")) and not bool(getattr(args, "artifact_probe_warn_only", False)):
            print_json(payload)
            raise SystemExit(1)
    print_json(payload)


def cmd_request_scene_assert(args):
    response = invoke_bridge(
        args.project_root,
        "unity.scene.assert",
        {
            "expectedName": args.expected_name or "",
            "expectedPath": args.expected_path or "",
            "requiredRootNames": args.required_root_name or None,
            "allowDirty": args.allow_dirty,
        },
        args.timeout_ms,
    )
    print_json(response)


def cmd_request_console_grep(args):
    response = invoke_bridge(
        args.project_root,
        "unity.console.grep",
        {
            "pattern": args.pattern,
            "regex": bool(args.regex),
            "ignoreCase": bool(args.ignore_case),
            "includeStackTraces": bool(args.include_stack_traces),
            "limit": max(1, int(args.limit or 20)),
            "includeTypes": args.include_type or None,
        },
        args.timeout_ms,
    )
    print_json(response)


def cmd_request_loading_timing(args):
    project_root = ensure_project_root(args.project_root)
    summary = request_loading_timing_summary(
        project_root=project_root,
        markers=args.marker or [],
        timing_only=not bool(args.include_non_timing),
        include_stack_traces=bool(args.include_stack_traces),
        include_types=args.include_type or [],
        limit=int(args.limit or 20),
        timeout_ms=int(args.timeout_ms or 5000),
        invoke_bridge=invoke_bridge,
    )
    print_json(summary)
    if not bool(summary.get("succeeded")):
        raise SystemExit(1)


def cmd_request_editor_quit(args):
    project_root = ensure_project_root(args.project_root)
    response = request_editor_quit(str(project_root), args.timeout_ms)
    response["quit_request_accepted"] = response.get("status") == "ok"
    response["process_exit_verified"] = False
    if not bool(getattr(args, "wait_for_exit", False)):
        print_json(response)
        return

    verification = verify_project_editor_closed(project_root, args.exit_timeout_ms)
    payload = {
        "action": "request_editor_quit",
        "project_root": str(project_root),
        "quit_request": response,
        "quit_request_accepted": response.get("status") == "ok",
        "quit_request_id": str(response.get("request_id") or ""),
        "quit_request_status": str(response.get("status") or ""),
    }
    payload.update(verification)
    if bool(payload.get("same_project_editor_closed")):
        payload["closeout_classification"] = "quit_ack_and_process_exit_verified"
        payload["recommended_next_action"] = "none"
        payload["next_distinct_action"] = "rerun_closed_editor_batch_lane"
        print_json(payload)
        return

    if not bool(payload.get("process_visibility_available")):
        payload["closeout_classification"] = "process_visibility_restricted"
        payload["recommended_next_action"] = "restore_host_process_visibility"
        payload["next_distinct_action"] = "restore_host_process_visibility"
        raise ToolInvocationError(
            "process_visibility_restricted",
            (
                "Unity quit request was acknowledged, but host process visibility is unavailable, "
                "so process exit cannot be verified."
            ),
            payload,
        )

    payload["closeout_classification"] = "editor_quit_ack_without_exit"
    payload["recommended_next_action"] = "manual_editor_close"
    payload["next_distinct_action"] = "manual_editor_close_or_terminate_then_verify_closed"
    raise ToolInvocationError(
        "editor_quit_ack_without_exit",
        (
            "Unity quit request was acknowledged, but the same-project editor process is still live. "
            f"Live editor pid(s): {', '.join(str(pid) for pid in payload.get('live_project_editor_pids') or [])}."
        ),
        payload,
    )


def cmd_verify_editor_closed(args):
    project_root = ensure_project_root(args.project_root)
    payload = verify_project_editor_closed(project_root, args.timeout_ms)
    if bool(payload.get("same_project_editor_closed")):
        print_json(payload)
        return

    if not bool(payload.get("process_visibility_available")):
        raise ToolInvocationError(
            "process_visibility_restricted",
            "Host process visibility is unavailable, so same-project editor closure cannot be verified.",
            payload,
        )

    raise ToolInvocationError(
        "editor_still_running",
        (
            "The same-project Unity editor is still running. "
            f"Live editor pid(s): {', '.join(str(pid) for pid in payload.get('live_project_editor_pids') or [])}."
        ),
        payload,
    )


def cmd_request_project_refresh(args):
    project_root = ensure_project_root(args.project_root)
    response = invoke_bridge(
        str(project_root),
        "unity.project.refresh",
        {
            "forceAssetRefresh": args.force_asset_refresh,
            "resolvePackages": args.resolve_packages,
            "rerunHealthProbe": args.rerun_health_probe,
        },
        resolve_operation_default_timeout_ms(project_root, "unity.project.refresh", 180000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_edm4u_resolve(args):
    project_root = ensure_project_root(args.project_root)
    response = invoke_bridge(
        str(project_root),
        "unity.edm4u.resolve",
        {
            "platform": args.platform,
            "force": args.force,
            "refreshBefore": args.refresh_before,
            "refreshAfter": args.refresh_after,
            "menuPathCandidates": args.menu_path_candidate or None,
        },
        resolve_operation_default_timeout_ms(project_root, "unity.edm4u.resolve", 300000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_sdk_dependency_verify(args):
    project_root = ensure_project_root(args.project_root)
    config_path = Path(args.config_file).expanduser()
    if not config_path.is_absolute():
        config_path = (Path.cwd() / config_path).resolve()
    config = read_json(config_path)
    if not isinstance(config, dict):
        raise ToolInvocationError("invalid_dependency_verify_config", "Dependency verification config must be a JSON object.")

    response = invoke_bridge(
        str(project_root),
        "unity.sdk.dependency.verify",
        config,
        resolve_operation_default_timeout_ms(project_root, "unity.sdk.dependency.verify", 30000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_editmode_tests(args):
    project_root = ensure_project_root(args.project_root)
    response = invoke_bridge(
        str(project_root),
        "unity.tests.run_editmode",
        {
            "testNames": args.test_names or None,
            "groupNames": args.group_names or None,
            "categoryNames": args.category_names or None,
            "assemblyNames": args.assembly_names or None,
        },
        resolve_operation_default_timeout_ms(project_root, "unity.tests.run_editmode", 300000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_playmode_tests(args):
    project_root = ensure_project_root(args.project_root)
    request_args = {
        "testNames": args.test_names or None,
        "groupNames": args.group_names or None,
        "categoryNames": args.category_names or None,
        "assemblyNames": args.assembly_names or None,
    }
    timeout_ms = resolve_operation_default_timeout_ms(project_root, "unity.tests.run_playmode", 300000) if args.timeout_ms is None else args.timeout_ms
    response = invoke_bridge(
        str(project_root),
        "unity.tests.run_playmode",
        request_args,
        timeout_ms,
    )

    error_code = _bridge_error_code(response)
    if error_code == "playmode_state_invalid":
        invoke_bridge(
            str(project_root),
            "unity.playmode.set",
            {"action": "exit"},
            resolve_operation_default_timeout_ms(project_root, "unity.playmode.set", 180000),
        )
        response = invoke_bridge(
            str(project_root),
            "unity.tests.run_playmode",
            request_args,
            timeout_ms,
        )

    print_json(response)


def cmd_request_compile(args):
    project_root = ensure_project_root(args.project_root)
    response = invoke_bridge(
        str(project_root),
        "unity.compile.player_scripts",
        {
            "name": args.name,
            "target": args.target,
            "optionFlags": args.option_flags,
            "extraDefines": args.extra_defines,
        },
        resolve_operation_default_timeout_ms(project_root, "unity.compile.player_scripts", 180000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_compile_matrix(args):
    project_root = ensure_project_root(args.project_root)
    config_file = Path(args.config_file).expanduser().resolve()
    if not config_file.is_file():
        raise ToolInvocationError("compile_matrix_config_not_found", f"Compile matrix config file not found: {config_file}")

    try:
        matrix_args = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolInvocationError("compile_matrix_config_invalid", str(exc)) from exc

    response = invoke_bridge(
        str(project_root),
        "unity.compile.matrix",
        matrix_args,
        resolve_operation_default_timeout_ms(project_root, "unity.compile.matrix", 300000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_build_config_compile_matrix(args):
    project_root = ensure_project_root(args.project_root)
    compile_plan = build_compile_matrix_args_from_build_config(
        project_root=project_root,
        build_config_asset=args.build_config_asset,
        requested_profiles=args.profile,
        requested_targets=args.target,
        stop_on_first_failure=args.stop_on_first_failure,
        tool_error_type=ToolInvocationError,
    )
    response = invoke_bridge(
        str(project_root),
        "unity.compile.matrix",
        compile_plan["matrixArgs"],
        resolve_operation_default_timeout_ms(project_root, "unity.compile.matrix", 300000) if args.timeout_ms is None else args.timeout_ms,
    )

    payload = {
        "build_config_asset": compile_plan["assetPath"],
        "profiles": compile_plan["profiles"],
        "bridge_response": response,
    }
    print_json(payload)


def cmd_project_action_list(args):
    project_root = ensure_project_root(args.project_root)
    catalog = load_project_action_catalog(project_root, args.catalog_file or "")
    print_json(project_action_catalog_payload(catalog))


def cmd_project_action_invoke(args):
    project_root = ensure_project_root(args.project_root)
    result, is_error = invoke_project_action_from_catalog(
        project_root=project_root,
        requested_action=args.action_id,
        action_payload=load_project_action_payload_args(args),
        catalog_path=args.catalog_file or "",
        scenario_name=args.scenario_name or "",
        timeout_ms=resolve_operation_default_timeout_ms(project_root, "unity.scenario.run", 600000) if args.timeout_ms is None else args.timeout_ms,
        poll_interval_ms=args.poll_interval_ms,
        wait_for_result=not bool(args.no_wait),
        allow_mutating=bool(args.allow_mutating),
    )
    print_json(result)
    if is_error:
        raise SystemExit(1)


def cmd_project_hook_scaffold(args):
    result = scaffold_project_hook(
        hook_name=args.hook_name,
        action_id=args.action_id,
        class_name=args.class_name,
        namespace=args.namespace,
        output_dir=Path(args.output_dir).expanduser().resolve(),
        mutating=bool(args.mutating),
        write_files=bool(args.write),
    )
    print_json(result)


def cmd_artifact_register(args):
    project_root = ensure_project_root(args.project_root)
    payload = register_artifact(
        project_root=project_root,
        artifact_path=args.path,
        destination=args.destination,
        kind=args.kind,
        producer=args.producer,
        artifact_schema_version=args.artifact_schema_version,
        language=args.language,
        retention_policy=args.retention_policy,
        metadata=load_optional_json_object(args.metadata_json, "artifact_metadata_invalid"),
        workspace_root=args.workspace_root,
        allow_unity_assets=bool(args.allow_unity_assets),
    )
    print_json(payload)


def cmd_artifact_write_report(args):
    project_root = ensure_project_root(args.project_root)
    payload = write_artifact_report(
        project_root=project_root,
        content=load_report_content_args(args),
        destination=args.destination,
        category=args.category,
        relative_path=args.relative_path,
        kind=args.kind,
        producer=args.producer,
        artifact_schema_version=args.artifact_schema_version,
        language=args.language,
        retention_policy=args.retention_policy,
        metadata=load_optional_json_object(args.metadata_json, "artifact_metadata_invalid"),
        workspace_root=args.workspace_root,
        allow_unity_assets=bool(args.allow_unity_assets),
    )
    print_json(payload)


def cmd_request_scenario_validate(args):
    project_root = ensure_project_root(args.project_root)
    scenario = normalize_project_action_scenario(
        project_root=project_root,
        scenario=load_json_file(args.scenario_file, "scenario_file_invalid"),
    )
    response = invoke_bridge(
        str(project_root),
        "unity.scenario.validate",
        {"scenario": scenario},
        args.timeout_ms,
    )
    print_json(response)


def cmd_request_scenario_run(args):
    project_root = ensure_project_root(args.project_root)
    scenario = normalize_project_action_scenario(
        project_root=project_root,
        scenario=load_json_file(args.scenario_file, "scenario_file_invalid"),
    )
    response = invoke_bridge(
        str(project_root),
        "unity.scenario.run",
        {"scenario": scenario},
        resolve_operation_default_timeout_ms(project_root, "unity.scenario.run", 600000) if args.timeout_ms is None else args.timeout_ms,
    )
    print_json(response)


def cmd_request_scenario_run_and_wait(args):
    project_root = ensure_project_root(args.project_root)
    scenario = normalize_project_action_scenario(
        project_root=project_root,
        scenario=load_json_file(args.scenario_file, "scenario_file_invalid"),
    )
    result = call_unity_scenario_run_and_wait_tool(
        {
            "projectRoot": str(project_root),
            "scenario": scenario,
            "timeoutMs": args.timeout_ms,
            "pollIntervalMs": args.poll_interval_ms,
        }
    )
    print_json(result.get("structuredContent") or {})
    if result.get("isError"):
        raise SystemExit(1)


def cmd_request_scenario_result(args):
    bridge_args: dict[str, Any] = {}
    if args.run_id:
        bridge_args["runId"] = args.run_id
    if args.scenario_name:
        bridge_args["scenarioName"] = args.scenario_name

    response = invoke_bridge(
        args.project_root,
        "unity.scenario.result",
        bridge_args,
        args.timeout_ms,
    )
    print_json(response)


def cmd_request_scenario_result_summary(args):
    project_root = ensure_project_root(args.project_root)
    bridge_args: dict[str, Any] = {}
    if args.run_id:
        bridge_args["runId"] = args.run_id
    if args.scenario_name:
        bridge_args["scenarioName"] = args.scenario_name

    try:
        response = invoke_bridge(
            str(project_root),
            "unity.scenario.result",
            bridge_args,
            args.timeout_ms,
        )
    except ToolInvocationError as exc:
        if exc.code in DISCOVERY_STATUS_FALLBACK_ERROR_CODES.union(SCENARIO_RECOVERY_ERROR_CODES):
            print_json(
                build_discovery_scenario_result_summary_for_error(
                    project_root,
                    bridge_args.get("runId", ""),
                    bridge_args.get("scenarioName", ""),
                    exc,
                )
            )
            return
        raise

    tool_result = bridge_response_to_tool_result(response)
    if tool_result.get("isError"):
        print_json(tool_result.get("structuredContent") or {})
        raise SystemExit(1)
    payload = tool_result.get("structuredContent") or {}
    print_json(build_scenario_result_summary_from_context(project_root, payload if isinstance(payload, dict) else {}))


def cmd_request_scenario_results_list(args):
    project_root = ensure_project_root(args.project_root)
    print_json(
        list_persisted_scenario_result_summaries(
            project_root,
            scenario_results_dir=scenario_results_dir,
            read_json=read_json,
            parse_utc_timestamp=parse_utc_timestamp,
            attach_persisted_scenario_result_evidence=attach_persisted_scenario_result_evidence,
            build_scenario_result_summary=build_scenario_result_summary,
            scenario_terminal_statuses=SCENARIO_TERMINAL_STATUSES,
            scenario_name=str(args.scenario_name or ""),
            limit=int(args.limit or 20),
        )
    )


def cmd_request_scenario_result_latest(args):
    project_root = ensure_project_root(args.project_root)
    print_json(
        latest_persisted_scenario_result_summary(
            project_root,
            scenario_results_dir=scenario_results_dir,
            read_json=read_json,
            parse_utc_timestamp=parse_utc_timestamp,
            attach_persisted_scenario_result_evidence=attach_persisted_scenario_result_evidence,
            build_scenario_result_summary=build_scenario_result_summary,
            scenario_terminal_statuses=SCENARIO_TERMINAL_STATUSES,
            scenario_name=str(args.scenario_name or ""),
        )
    )


def cmd_maintenance_prune(args):
    project_root = ensure_project_root(args.project_root)
    result = prune_project_artifacts(
        project_root,
        {
            "dryRun": args.dry_run,
            "requestJournalMaxAgeHours": args.request_journal_max_age_hours,
            "requestJournalKeepLatest": args.request_journal_keep_latest,
            "scenarioSuccessMaxAgeHours": args.scenario_success_max_age_hours,
            "scenarioFailureMaxAgeHours": args.scenario_failure_max_age_hours,
            "scenarioRunningMaxAgeHours": args.scenario_running_max_age_hours,
            "scenarioKeepLatestSuccess": args.scenario_keep_latest_success,
            "scenarioKeepLatestFailure": args.scenario_keep_latest_failure,
            "scenarioKeepLatestRunning": args.scenario_keep_latest_running,
            "capturesMaxAgeHours": args.captures_max_age_hours,
            "capturesKeepLatest": args.captures_keep_latest,
            "pruneLogs": args.prune_logs,
            "logsMaxAgeHours": args.logs_max_age_hours,
            "logsKeepLatest": args.logs_keep_latest,
        },
        bridge_root=bridge_root,
        request_journal_dir=request_journal_dir,
        scenario_results_dir=scenario_results_dir,
        active_scenario_run_path=active_scenario_run_path,
        captures_dir=captures_dir,
        logs_dir=logs_dir,
        default_editor_log_path=default_editor_log_path,
        read_json=read_json,
    )
    print_json(result)


def cmd_open_editor(args):
    project_root = ensure_project_root(args.project_root)
    unity_app = detect_unity_app_path_for_project(project_root, args.unity_app)
    log_path = resolve_editor_log_path(project_root, args.editor_log_path)
    payload = open_unity_editor(project_root, log_path, unity_app, args.background_open)
    payload["project_root"] = str(project_root)
    refresh_project_context(project_root)
    print_json(payload)


def cmd_ensure_ready(args):
    project_root = ensure_project_root(args.project_root)
    log_path = resolve_editor_log_path(project_root, args.editor_log_path)
    package_import_state_before_ready = inspect_light_mcp_import_state(project_root)

    payload: dict[str, Any] = {
        "project_root": str(project_root),
        "editor_log_path": str(log_path),
        "startup_policy": args.startup_policy,
        "package_import_state": package_import_state_before_ready,
        "package_import_state_before_ready": package_import_state_before_ready,
    }
    payload["discovery"] = build_project_discovery_report(project_root)

    try:
        if not args.open_editor:
            maybe_fail_fast_offline_ensure_ready_without_open(
                project_root,
                payload["discovery"],
            )
        current_state = current_project_context_bridge_state(project_root)

        if args.open_editor and bridge_state_is_ready(current_state, args.heartbeat_max_age_seconds):
            payload["launch"] = {
                "reused_existing_editor": True,
                "reused_via": "healthy_bridge_state",
                "editor_pid": int(current_state.get("editor_pid") or 0),
                "unity_version": str(current_state.get("unity_version") or ""),
            }
        elif args.open_editor:
            unity_app = detect_unity_app_path_for_project(project_root, args.unity_app)
            payload["launch"] = open_unity_editor(project_root, log_path, unity_app, args.background_open)

        state = wait_for_ready(
            project_root=project_root,
            timeout_ms=args.timeout_ms,
            heartbeat_max_age_seconds=args.heartbeat_max_age_seconds,
            startup_policy=args.startup_policy,
            editor_log_path=log_path,
        )
    except ToolInvocationError as exc:
        if str(exc.details.get("fail_fast_reason") or "") == "ensure_ready_without_open_editor_offline":
            raise
        details = dict(exc.details or {})
        package_import_state = inspect_light_mcp_import_state(project_root)
        details["package_import_state"] = package_import_state
        import_state = str(package_import_state.get("import_state") or "")
        discovery = build_project_discovery_report(project_root)
        live_editor_pids: list[int] = []
        for pid_value in discovery.get("detected_editor_pids") or discovery.get("live_project_editor_pids") or []:
            try:
                pid = int(pid_value or 0)
            except (TypeError, ValueError):
                continue
            if pid > 0:
                live_editor_pids.append(pid)
        bridge_state_present = bool(package_import_state.get("bridge_state_present")) or bool(
            current_project_context_bridge_state(project_root)
        )
        if (
            args.open_editor
            and import_state in {"declared_not_resolved", "resolved_not_cached"}
            and live_editor_pids
            and not bridge_state_present
        ):
            details["package_import_diagnosis"] = "package_declared_not_imported"
            details["recommended_next_action"] = "reopen_project_for_clean_resolve"
            details["next_distinct_action"] = "close_and_reopen_unity_to_resolve_package"
            details["recommended_recovery_command"] = (
                f"xuunity_light_unity_mcp.sh ensure-ready --project-root {project_root} --open-editor"
            )
            details["live_project_editor_pids"] = live_editor_pids
        raise enrich_tool_invocation_error_with_discovery(
            project_root,
            ToolInvocationError(exc.code, exc.message, details),
        )

    payload["bridge_state"] = state
    if payload.get("launch") and not bool(payload["launch"].get("reused_existing_editor")):
        update_host_editor_session_pid(project_root, int(state.get("editor_pid") or 0))
    refresh_project_context(project_root)
    payload["discovery_after_ready"] = build_project_discovery_report(project_root)
    payload["package_dependency"] = inspect_package_dependency_alignment(project_root)
    payload["package_import_state"] = inspect_light_mcp_import_state(project_root)
    payload["package_import_state_after_ready"] = payload["package_import_state"]
    print_json(payload)


def cmd_restore_editor_state(args):
    project_root = ensure_project_root(args.project_root)
    payload = restore_host_opened_editor_state(project_root, args.timeout_ms, request_editor_quit)
    refresh_project_context(project_root)
    payload["post_close_discovery"] = build_project_discovery_report(project_root)
    if bool(payload.get("host_opened_session_found")) and not bool(payload.get("closeout_verified")):
        closeout_classification = str(payload.get("closeout_classification") or "restore_editor_state_incomplete")
        recommended_next_action = str(payload.get("recommended_next_action") or "inspect_project_editor_processes")
        recommended_recovery_command = str(payload.get("recommended_recovery_command") or "")
        message = (
            "Host-opened editor closeout did not reach verified process exit. "
            f"closeout_classification: {closeout_classification} "
            f"recommended_next_action: {recommended_next_action}"
        )
        if recommended_recovery_command:
            message += f" next_step: {recommended_recovery_command}"
        raise ToolInvocationError("restore_editor_state_incomplete", message, payload)
    if bool(getattr(args, "require_closed", False)) and not bool(payload.get("same_project_editor_closed")):
        if not bool(payload.get("process_visibility_available")):
            raise ToolInvocationError(
                "process_visibility_restricted",
                "Host process visibility is unavailable, so restore-editor-state --require-closed cannot verify closure.",
                payload,
            )
        raise ToolInvocationError(
            "restore_editor_state_incomplete",
            (
                "restore-editor-state --require-closed did not reach verified same-project editor closure. "
                f"Live editor pid(s): {', '.join(str(pid) for pid in payload.get('live_project_editor_pids') or [])}."
            ),
            payload,
        )
    print_json(payload)


def cmd_runtime_config_show(args):
    project_root = ensure_project_root(args.project_root)
    print_json(build_runtime_config_report(project_root))


def cmd_project_discovery_report(args):
    project_root = ensure_project_root(args.project_root)
    print_json(build_project_discovery_report(project_root))


def cmd_registry_context_report(args):
    print_json(build_registry_context_report())


def cmd_registry_prune_contexts(args):
    pruned = prune_stale_project_contexts(
        offline_context_max_idle_seconds=args.offline_context_max_idle_seconds,
        general_context_max_idle_seconds=args.general_context_max_idle_seconds,
    )
    print_json(
        {
            "pruned_count": len(pruned),
            "pruned": pruned,
            "remaining": build_registry_context_report(),
        }
    )


def cmd_batch_test_framework_version_regression(args):
    project_root = ensure_project_root(args.project_root)
    project_manifest_path = project_root / "Packages" / "manifest.json"
    packages_lock_path = project_root / "Packages" / "packages-lock.json"

    package_source = find_repo_local_package_source(project_root)
    if package_source is None:
        raise ToolInvocationError(
            "repo_local_package_source_not_found",
            (
                "Could not locate the repo-local XUUnityLightUnityMcp package source from this project root. "
                "Run devmode first so the project points at the local AIRoot package."
            ),
        )
    package_manifest_path = package_source / "package.json"

    original_state = read_test_framework_state(
        project_root,
        project_manifest_path,
        package_manifest_path,
        packages_lock_path,
    )
    requested_versions = normalize_requested_versions(list(args.version or []), args.versions_file)
    if not requested_versions:
        requested_versions = [str(original_state.get("project_manifest_dependency") or "")]

    focus_assemblies = list(args.focus_assembly_name or [])
    focus_tests = list(args.focus_test_name or [])
    generated_focus_fixture: dict[str, Any] = {}
    if not focus_assemblies and not focus_tests and not bool(args.no_generated_focus_test):
        generated_focus_fixture = deploy_test_framework_regression_focus_fixture(
            project_root,
            args.generated_focus_relative_dir,
        )
        focus_tests = [TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_TEST_NAME]
    broad_assemblies = list(args.broad_assembly_name or [])
    compile_target = str(args.compile_target or TEST_FRAMEWORK_REGRESSION_COMPILE_TARGET).strip()
    if not compile_target:
        compile_target = TEST_FRAMEWORK_REGRESSION_COMPILE_TARGET

    live_editor_pids = list_live_project_editor_pids(project_root)
    host_session = current_project_context_host_session_state(project_root)
    tracked_host_pid = int(host_session.get("editor_pid") or 0)
    host_managed_live_editor = bool(host_session.get("opened_by_host")) and tracked_host_pid > 0 and tracked_host_pid in live_editor_pids
    if live_editor_pids and not host_managed_live_editor:
        raise ToolInvocationError(
            "editor_running_regression_conflict",
            (
                "Refusing to start test-framework version regression while this project is open in a non-host-managed "
                f"Unity editor session. Live editor pid(s): {', '.join(str(pid) for pid in live_editor_pids)}. "
                "Close the editor first, or reopen it through ensure-ready so the host can restore it safely."
            ),
            {
                "live_editor_pids": live_editor_pids,
                "tracked_host_pid": tracked_host_pid,
            },
        )

    result_path = (
        Path(args.result_file).expanduser().resolve()
        if args.result_file
        else test_framework_regression_result_path(project_root)
    )
    artifacts_dir = test_framework_regression_artifacts_dir(result_path)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    overall_result: dict[str, Any] = {
        "action": "batch_test_framework_version_regression",
        "project_root": str(project_root),
        "result_file": str(result_path),
        "artifacts_dir": str(artifacts_dir),
        "requested_versions": requested_versions,
        "initial_editor_state": {
            "live_editor_pids": live_editor_pids,
            "host_managed_live_editor": host_managed_live_editor,
            "tracked_host_pid": tracked_host_pid,
            "restore_editor_open_state": bool(live_editor_pids),
        },
        "focus_assemblies": focus_assemblies,
        "focus_tests": focus_tests,
        "generated_focus_fixture": generated_focus_fixture,
        "broad_assemblies": broad_assemblies,
        "compile_target": compile_target,
        "original_state": original_state,
        "candidates": [],
        "restoration": {},
    }

    baseline_result: dict[str, Any] | None = None

    try:
        if live_editor_pids and host_managed_live_editor:
            preclose_output = run_self_json_command(
                [
                    "restore-editor-state",
                    "--project-root",
                    str(project_root),
                    "--timeout-ms",
                    "30000",
                ]
            )
            write_test_framework_step_artifact(artifacts_dir / "preclose_editor.json", preclose_output)
            overall_result["initial_editor_state"]["preclose"] = summarize_bridge_step(preclose_output)

        for requested_version in requested_versions:
            candidate_result = run_single_test_framework_candidate(
                project_root=project_root,
                requested_version=requested_version,
                project_manifest_path=project_manifest_path,
                package_manifest_path=package_manifest_path,
                packages_lock_path=packages_lock_path,
                artifacts_dir=artifacts_dir,
                compile_target=compile_target,
                focus_assemblies=focus_assemblies,
                focus_tests=focus_tests,
                broad_assemblies=broad_assemblies,
            )
            overall_result["candidates"].append(candidate_result)
            if requested_version == str(original_state.get("project_manifest_dependency") or ""):
                baseline_result = candidate_result
    finally:
        restoration: dict[str, Any] = {
            "restore_original_version": bool(args.restore_original_version),
        }
        if args.restore_original_version:
            write_declared_dependency_version(
                project_manifest_path,
                TEST_FRAMEWORK_PACKAGE_NAME,
                str(original_state.get("project_manifest_dependency") or ""),
            )
            write_declared_dependency_version(
                package_manifest_path,
                TEST_FRAMEWORK_PACKAGE_NAME,
                str(original_state.get("package_manifest_dependency") or ""),
            )
            restoration["removed_lock_entries"] = remove_lock_dependencies(
                packages_lock_path,
                TEST_FRAMEWORK_REGRESSION_LOCK_PACKAGES,
            )
            restoration["state_after_restore_patch"] = read_test_framework_state(
                project_root,
                project_manifest_path,
                package_manifest_path,
                packages_lock_path,
            )
            if bool(overall_result["initial_editor_state"].get("restore_editor_open_state")):
                reopen_output = run_self_json_command(
                    [
                        "ensure-ready",
                        "--project-root",
                        str(project_root),
                        "--open-editor",
                        "--timeout-ms",
                        "180000",
                    ]
                )
                write_test_framework_step_artifact(artifacts_dir / "restore_editor_open_state.json", reopen_output)
                restoration["reopen_editor"] = summarize_bridge_step(reopen_output)
                restoration["state_after_reopen"] = read_test_framework_state(
                    project_root,
                    project_manifest_path,
                    package_manifest_path,
                    packages_lock_path,
                )
        if generated_focus_fixture:
            restoration["generated_focus_fixture_cleanup"] = cleanup_test_framework_regression_focus_fixture(
                generated_focus_fixture
            )
        overall_result["restoration"] = restoration

    if baseline_result is not None:
        for candidate_result in overall_result["candidates"]:
            candidate_result["broad_suite_vs_baseline"] = compare_candidate_to_baseline(
                baseline_result,
                candidate_result,
            )

    overall_result["summary"] = {
        "candidate_count": len(overall_result["candidates"]),
        "contract_passed_versions": [
            candidate_result.get("requested_version")
            for candidate_result in overall_result["candidates"]
            if bool(((candidate_result.get("contract") or {}).get("contract_passed")))
        ],
        "baseline_version": baseline_result.get("requested_version") if baseline_result else "",
    }

    result_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(result_path, overall_result)
    print_json(overall_result)

    if any(not bool(((candidate_result.get("contract") or {}).get("contract_passed"))) for candidate_result in overall_result["candidates"]):
        raise SystemExit(1)


def cmd_batch_compile(args):
    project_root = ensure_project_root(args.project_root)
    unity_app = detect_unity_app_path_for_project(project_root, args.unity_app)
    build_target = str(args.target or "").strip()
    if not build_target:
        raise ToolInvocationError("missing_build_target", "--target is required.")

    operation_suffix = build_target if not args.name else f"{build_target}_{args.name}"
    log_path = (
        Path(args.batch_log_path).expanduser().resolve()
        if args.batch_log_path
        else default_batch_operation_log_path(project_root, f"compile_{operation_suffix}")
    )
    result_path = (
        Path(args.result_file).expanduser().resolve()
        if args.result_file
        else default_batch_operation_result_path(project_root, f"compile_{operation_suffix}")
    )

    extra_args = [
        "--xuunity-build-target",
        build_target,
    ]
    if args.name:
        extra_args.extend(["--xuunity-compile-name", args.name])
    for option_flag in list(args.option_flag or []):
        extra_args.extend(["--xuunity-option-flag", option_flag])
    for extra_define in list(args.extra_define or []):
        extra_args.extend(["--xuunity-extra-define", extra_define])

    command = build_batch_validation_command(
        project_root=project_root,
        unity_app=unity_app,
        log_path=log_path,
        result_path=result_path,
        action="compile-player-scripts",
        extra_args=extra_args,
    )
    payload = {
        "action": "batch_compile_player_scripts",
        "project_root": str(project_root),
        "unity_app": str(unity_app),
        "build_target": build_target,
        "compile_name": args.name or "",
        "option_flags": list(args.option_flag or []),
        "extra_defines": list(args.extra_define or []),
        "log_path": str(log_path),
        "result_file": str(result_path),
        "command": command,
        "dry_run": args.dry_run,
    }
    run_batch_operation(
        project_root=project_root,
        unity_app=unity_app,
        command=command,
        payload=payload,
        log_path=log_path,
        result_path=result_path,
        dry_run=args.dry_run,
        timeout_ms=args.timeout_ms,
        workspace_root=resolve_workspace_root(project_root, getattr(args, "workspace_root", None)),
        side_effect_mode=getattr(args, "side_effect_mode", "git"),
        side_effect_allow_config=load_batch_side_effect_allow_config(getattr(args, "side_effect_allow_file", None)),
        progress_interval_seconds=float(getattr(args, "progress_interval_seconds", DEFAULT_BATCH_PROGRESS_INTERVAL_SECONDS)),
        progress_stdout=progress_stdout_enabled(args),
        batch_fallback_mode=getattr(args, "batch_fallback_mode", "auto"),
        refresh_license=bool(getattr(args, "refresh_license", False)),
        gui_operation="unity.compile.player_scripts",
        gui_operation_args={
            "name": args.name,
            "target": build_target,
            "optionFlags": list(args.option_flag or []),
            "extraDefines": list(args.extra_define or []),
        },
    )


def cmd_batch_compile_matrix(args):
    project_root = ensure_project_root(args.project_root)
    unity_app = detect_unity_app_path_for_project(project_root, args.unity_app)
    config_file = Path(args.config_file).expanduser().resolve()
    if not config_file.is_file():
        raise ToolInvocationError("compile_matrix_config_not_found", f"Compile matrix config file not found: {config_file}")

    log_path = (
        Path(args.batch_log_path).expanduser().resolve()
        if args.batch_log_path
        else default_batch_operation_log_path(project_root, "compile_matrix")
    )
    result_path = (
        Path(args.result_file).expanduser().resolve()
        if args.result_file
        else default_batch_operation_result_path(project_root, "compile_matrix")
    )

    from server_host_platform import is_wsl, wsl_to_windows_path
    config_file_host = wsl_to_windows_path(config_file) if is_wsl() else str(config_file)
    command = build_batch_validation_command(
        project_root=project_root,
        unity_app=unity_app,
        log_path=log_path,
        result_path=result_path,
        action="compile-matrix",
        extra_args=["--xuunity-config-file", config_file_host],
    )
    payload = {
        "action": "batch_compile_matrix",
        "project_root": str(project_root),
        "unity_app": str(unity_app),
        "config_file": str(config_file),
        "log_path": str(log_path),
        "result_file": str(result_path),
        "command": command,
        "dry_run": args.dry_run,
    }
    run_batch_operation(
        project_root=project_root,
        unity_app=unity_app,
        command=command,
        payload=payload,
        log_path=log_path,
        result_path=result_path,
        dry_run=args.dry_run,
        timeout_ms=args.timeout_ms,
        workspace_root=resolve_workspace_root(project_root, getattr(args, "workspace_root", None)),
        side_effect_mode=getattr(args, "side_effect_mode", "git"),
        side_effect_allow_config=load_batch_side_effect_allow_config(getattr(args, "side_effect_allow_file", None)),
        progress_interval_seconds=float(getattr(args, "progress_interval_seconds", DEFAULT_BATCH_PROGRESS_INTERVAL_SECONDS)),
        progress_stdout=progress_stdout_enabled(args),
        batch_fallback_mode=getattr(args, "batch_fallback_mode", "auto"),
        refresh_license=bool(getattr(args, "refresh_license", False)),
        gui_operation="unity.compile.matrix",
        gui_operation_args=load_json_file(str(config_file), "compile_matrix_config_invalid"),
    )


def cmd_batch_build_config_compile_matrix(args):
    project_root = ensure_project_root(args.project_root)
    unity_app = detect_unity_app_path_for_project(project_root, args.unity_app)
    compile_plan = build_compile_matrix_args_from_build_config(
        project_root=project_root,
        build_config_asset=args.build_config_asset,
        requested_profiles=args.profile,
        requested_targets=args.target,
        stop_on_first_failure=args.stop_on_first_failure,
        tool_error_type=ToolInvocationError,
    )
    log_path = (
        Path(args.batch_log_path).expanduser().resolve()
        if args.batch_log_path
        else default_batch_operation_log_path(project_root, "build_config_compile_matrix")
    )
    result_path = (
        Path(args.result_file).expanduser().resolve()
        if args.result_file
        else default_batch_operation_result_path(project_root, "build_config_compile_matrix")
    )

    temp_dir = project_root / "Library" / "XUUnityLightMcp" / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(temp_dir),
        suffix="_xuunity_compile_matrix.json",
        delete=False,
    ) as temp_file:
        temp_config_path = Path(temp_file.name)
    try:
        temp_config_path.write_text(json.dumps(compile_plan["matrixArgs"], indent=2) + "\n", encoding="utf-8")
        from server_host_platform import is_wsl, wsl_to_windows_path
        temp_config_path_host = wsl_to_windows_path(temp_config_path) if is_wsl() else str(temp_config_path)
        command = build_batch_validation_command(
            project_root=project_root,
            unity_app=unity_app,
            log_path=log_path,
            result_path=result_path,
            action="compile-matrix",
            extra_args=["--xuunity-config-file", temp_config_path_host],
        )
        payload = {
            "action": "batch_build_config_compile_matrix",
            "project_root": str(project_root),
            "unity_app": str(unity_app),
            "build_config_asset": compile_plan["assetPath"],
            "profiles": compile_plan["profiles"],
            "generated_config_file": str(temp_config_path),
            "log_path": str(log_path),
            "result_file": str(result_path),
            "command": command,
            "dry_run": False,
        }
        run_batch_operation(
            project_root=project_root,
            unity_app=unity_app,
            command=command,
            payload=payload,
            log_path=log_path,
            result_path=result_path,
            dry_run=False,
            timeout_ms=args.timeout_ms,
            workspace_root=resolve_workspace_root(project_root, getattr(args, "workspace_root", None)),
            side_effect_mode=getattr(args, "side_effect_mode", "git"),
            side_effect_allow_config=load_batch_side_effect_allow_config(getattr(args, "side_effect_allow_file", None)),
            progress_interval_seconds=float(getattr(args, "progress_interval_seconds", DEFAULT_BATCH_PROGRESS_INTERVAL_SECONDS)),
            progress_stdout=progress_stdout_enabled(args),
            batch_fallback_mode=getattr(args, "batch_fallback_mode", "auto"),
            refresh_license=bool(getattr(args, "refresh_license", False)),
            gui_operation="unity.compile.matrix",
            gui_operation_args=compile_plan["matrixArgs"],
        )
    finally:
        try:
            temp_config_path.unlink()
        except OSError:
            pass


def cmd_batch_editmode_tests(args):
    project_root = ensure_project_root(args.project_root)
    require_test_framework_capability_for_batch(project_root)
    unity_app = detect_unity_app_path_for_project(project_root, args.unity_app)
    log_path = (
        Path(args.batch_log_path).expanduser().resolve()
        if args.batch_log_path
        else default_batch_operation_log_path(project_root, "editmode_tests")
    )
    result_path = (
        Path(args.result_file).expanduser().resolve()
        if args.result_file
        else default_batch_operation_result_path(project_root, "editmode_tests")
    )

    extra_args: list[str] = []
    for test_name in list(args.test_names or []):
        extra_args.extend(["--xuunity-test-name", test_name])
    for group_name in list(args.group_names or []):
        extra_args.extend(["--xuunity-group-name", group_name])
    for category_name in list(args.category_names or []):
        extra_args.extend(["--xuunity-category-name", category_name])
    for assembly_name in list(args.assembly_names or []):
        extra_args.extend(["--xuunity-assembly-name", assembly_name])

    command = build_batch_validation_command(
        project_root=project_root,
        unity_app=unity_app,
        log_path=log_path,
        result_path=result_path,
        action="editmode-tests",
        extra_args=extra_args,
    )
    payload = {
        "action": "batch_editmode_tests",
        "project_root": str(project_root),
        "unity_app": str(unity_app),
        "test_names": list(args.test_names or []),
        "group_names": list(args.group_names or []),
        "category_names": list(args.category_names or []),
        "assembly_names": list(args.assembly_names or []),
        "log_path": str(log_path),
        "result_file": str(result_path),
        "command": command,
        "dry_run": args.dry_run,
    }
    run_batch_operation(
        project_root=project_root,
        unity_app=unity_app,
        command=command,
        payload=payload,
        log_path=log_path,
        result_path=result_path,
        dry_run=args.dry_run,
        timeout_ms=args.timeout_ms,
        workspace_root=resolve_workspace_root(project_root, getattr(args, "workspace_root", None)),
        side_effect_mode=getattr(args, "side_effect_mode", "git"),
        side_effect_allow_config=load_batch_side_effect_allow_config(getattr(args, "side_effect_allow_file", None)),
        progress_interval_seconds=float(getattr(args, "progress_interval_seconds", DEFAULT_BATCH_PROGRESS_INTERVAL_SECONDS)),
        progress_stdout=progress_stdout_enabled(args),
        batch_fallback_mode=getattr(args, "batch_fallback_mode", "auto"),
        refresh_license=bool(getattr(args, "refresh_license", False)),
        gui_operation="unity.tests.run_editmode",
        gui_operation_args={
            "testNames": list(args.test_names or []) or None,
            "groupNames": list(args.group_names or []) or None,
            "categoryNames": list(args.category_names or []) or None,
            "assemblyNames": list(args.assembly_names or []) or None,
        },
    )


def cmd_test_results_table(args):
    project_roots = [_resolve_cli_project_root(value) for value in list(getattr(args, "project_root", []) or [])]
    if not project_roots and getattr(args, "workspace_root", None):
        project_roots = _discover_test_result_project_roots(Path(args.workspace_root).expanduser().resolve())

    result_files = [
        Path(value).expanduser().resolve()
        for value in list(getattr(args, "result_file", []) or [])
    ]
    if not project_roots and not result_files:
        raise ToolInvocationError(
            "test_results_project_required",
            "Provide --project-root, --workspace-root, or --result-file for test-results-table.",
        )

    rows = select_test_result_rows(
        project_roots=project_roots,
        modes=list(getattr(args, "mode", []) or []),
        request_ids=list(getattr(args, "request_id", []) or []),
        result_files=result_files,
    )
    print(
        format_test_results(
            rows,
            output_format=str(getattr(args, "format", "markdown") or "markdown"),
        ),
        end="",
    )


def _resolve_cli_project_root(value: str) -> Path:
    return ensure_project_root(value)


def _discover_test_result_project_roots(workspace_root: Path) -> list[Path]:
    if not workspace_root.is_dir():
        raise ToolInvocationError("workspace_root_not_found", f"Workspace root not found: {workspace_root}")
    roots: list[Path] = []
    for candidate in sorted(workspace_root.iterdir()):
        if (
            candidate.is_dir()
            and (candidate / "ProjectSettings" / "ProjectVersion.txt").is_file()
            and (candidate / "Packages" / "manifest.json").is_file()
        ):
            roots.append(candidate.resolve())
    return roots


def cmd_artifact_probe(args):
    artifact_probe_config = load_artifact_probe_config(
        artifact_probe_file=getattr(args, "artifact_probe_file", "") or "",
        artifact_probe_json=getattr(args, "artifact_probe_json", "") or "",
        tool_error_type=ToolInvocationError,
    )
    if artifact_probe_config is None:
        raise ToolInvocationError(
            "artifact_probe_missing",
            "Pass --artifact-probe-file or --artifact-probe-json.",
        )

    summary = run_artifact_probe(
        artifact_probe_config,
        artifact_path_override=args.artifact_path or "",
        truncate_text=truncate_text,
    )
    print_json({"artifact_probe_summary": summary})
    if not bool(summary.get("succeeded")) and not bool(args.artifact_probe_warn_only):
        raise SystemExit(1)


def cmd_batch_build_player(args):
    project_root = ensure_project_root(args.project_root)
    unity_app = detect_unity_app_path_for_project(project_root, args.unity_app)
    build_target = str(args.build_target or "").strip()
    if not build_target:
        raise ToolInvocationError("missing_build_target", "--build-target is required.")

    log_path = (
        Path(args.batch_log_path).expanduser().resolve()
        if args.batch_log_path
        else default_batch_build_log_path(project_root, build_target)
    )
    result_path = (
        Path(args.result_file).expanduser().resolve()
        if args.result_file
        else default_batch_build_result_path(project_root, build_target)
    )
    output_path = resolve_batch_build_output_path(project_root, args.output_path)
    from server_host_platform import is_wsl, wsl_to_windows_path
    output_path_windows = wsl_to_windows_path(output_path) if is_wsl() else output_path
    result_path_host = wsl_to_windows_path(result_path) if is_wsl() else str(result_path)
    scene_paths = list(args.scene_path or [])
    build_options = list(args.build_option or [])
    artifact_probe_config = load_artifact_probe_config(
        artifact_probe_file=getattr(args, "artifact_probe_file", "") or "",
        artifact_probe_json=getattr(args, "artifact_probe_json", "") or "",
        tool_error_type=ToolInvocationError,
    )
    artifact_probe_warn_only = bool(getattr(args, "artifact_probe_warn_only", False))

    command = build_plain_batch_build_command(
        project_root=project_root,
        unity_app=unity_app,
        log_path=log_path,
        result_path=result_path,
        build_target=build_target,
        output_path=output_path_windows,
        scene_paths=scene_paths,
        build_options=build_options,
    )

    payload: dict[str, Any] = {
        "action": "plain_batch_build",
        "project_root": str(project_root),
        "unity_app": str(unity_app),
        "build_target": build_target,
        "output_path": output_path,
        "scene_paths": scene_paths,
        "build_options": build_options,
        "log_path": str(log_path),
        "result_file": str(result_path),
        "command": command,
        "dry_run": args.dry_run,
        "artifact_probe_enabled": artifact_probe_config is not None,
        "artifact_probe_warn_only": artifact_probe_warn_only,
    }
    run_batch_operation(
        project_root=project_root,
        unity_app=unity_app,
        command=command,
        payload=payload,
        log_path=log_path,
        result_path=result_path,
        dry_run=args.dry_run,
        timeout_ms=args.timeout_ms,
        workspace_root=resolve_workspace_root(project_root, getattr(args, "workspace_root", None)),
        side_effect_mode=getattr(args, "side_effect_mode", "git"),
        side_effect_allow_config=load_batch_side_effect_allow_config(getattr(args, "side_effect_allow_file", None)),
        progress_interval_seconds=float(getattr(args, "progress_interval_seconds", DEFAULT_BATCH_PROGRESS_INTERVAL_SECONDS)),
        progress_stdout=progress_stdout_enabled(args),
        batch_fallback_mode=getattr(args, "batch_fallback_mode", "auto"),
        refresh_license=bool(getattr(args, "refresh_license", False)),
        gui_operation="unity.build_player",
        gui_operation_args={
            "buildTarget": build_target,
            "outputPath": output_path_windows,
            "resultFile": result_path_host,
            "scenePaths": scene_paths,
            "buildOptions": build_options,
        },
        artifact_probe_config=artifact_probe_config,
        artifact_probe_path_override=output_path,
        artifact_probe_warn_only=artifact_probe_warn_only,
        last_known_output_path=output_path,
    )


from server_core import wrap_globals_with_proxies
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
    "inspect_light_mcp_import_state",
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
