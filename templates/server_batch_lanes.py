# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def load_batch_side_effect_allow_config_data(
    path_value: str | None,
    *,
    load_side_effect_allow_file: Callable[..., dict[str, Any]],
    ToolInvocationError: Any,
) -> dict[str, Any]:
    return load_side_effect_allow_file(path_value or "", tool_error_type=ToolInvocationError)


def progress_stdout_enabled_data(args: Any) -> bool:
    return not bool(getattr(args, "no_progress_stdout", False))


def normalize_batch_fallback_mode_data(
    value: Any,
    *,
    ToolInvocationError: Any,
) -> str:
    mode = str(value or "auto").strip()
    if mode not in {"auto", "off", "require-batch"}:
        raise ToolInvocationError(
            "invalid_batch_fallback_mode",
            "--batch-fallback-mode must be one of: auto, off, require-batch.",
        )
    return mode


def batch_start_editor_state_data(
    project_root: Path,
    *,
    process_visibility_summary: Callable[[], dict[str, Any]],
    list_live_project_editor_pids: Callable[[Path], list[int]],
    try_read_live_editor_state: Callable[[Path], dict[str, Any]],
    current_project_context_bridge_state: Callable[[Path], dict[str, Any]],
    ToolInvocationError: Any,
) -> dict[str, Any]:
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


def gui_fallback_busy_reasons_data(
    project_root: Path,
    start_editor_state: dict[str, Any],
    *,
    try_read_live_editor_state: Callable[[Path], dict[str, Any]],
    current_project_context_bridge_state: Callable[[Path], dict[str, Any]],
    bridge_state_is_ready: Callable[[dict[str, Any], float], bool],
    DEFAULT_HEARTBEAT_MAX_AGE_SECONDS: float,
    ToolInvocationError: Any,
) -> list[str]:
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


def attach_license_lane_fields_data(payload: dict[str, Any], license_capabilities: dict[str, Any] | None) -> None:
    license_capabilities = dict(license_capabilities or {})
    payload["license_capabilities"] = license_capabilities
    payload["license_batchmode_supported"] = license_capabilities.get("batchmode_supported")
    payload["license_blocker_code"] = str(license_capabilities.get("batchmode_blocker_code") or "")
    payload["license_recommended_execution_lane"] = str(license_capabilities.get("recommended_execution_lane") or "")
    payload["batchmode_probe_log_path"] = str(license_capabilities.get("batchmode_probe_log_path") or "")


def attach_batch_lane_fields_to_summary_data(summary: dict[str, Any], payload: dict[str, Any]) -> None:
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


def batch_lane_preflight_blocker_data(
    *,
    project_root: Path,
    unity_app: Path,
    batch_fallback_mode: str,
    payload: dict[str, Any],
    action_label: str,
    timeout_ms: int | None,
    refresh_license: bool = False,
    normalize_batch_fallback_mode: Callable[[Any], str],
    batch_start_editor_state: Callable[[Path], dict[str, Any]],
    list_live_project_editor_pids: Callable[[Path], list[int]],
    build_license_capabilities: Callable[..., dict[str, Any]],
    attach_license_lane_fields: Callable[[dict[str, Any], dict[str, Any] | None], None],
    build_batch_editor_conflict_details: Callable[[Path, list[int]], dict[str, Any]],
    ToolInvocationError: Any,
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


def infer_gui_operation_succeeded_data(response: dict[str, Any], result_payload: dict[str, Any] | None) -> bool:
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


def run_gui_fallback_operation_data(
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
    output_mode: str = "full",
    batch_start_editor_state: Callable[[Path], dict[str, Any]],
    gui_fallback_busy_reasons: Callable[[Path, dict[str, Any]], list[str]],
    ToolInvocationError: Any,
    open_unity_editor: Callable[..., dict[str, Any]],
    wait_for_ready: Callable[..., dict[str, Any]],
    DEFAULT_HEARTBEAT_MAX_AGE_SECONDS: float,
    update_host_editor_session_pid: Callable[[Path, int], None],
    refresh_project_context: Callable[[Path], Any],
    restore_host_opened_editor_state: Callable[..., dict[str, Any]],
    request_editor_quit: Callable[[Path, int], dict[str, Any]],
    capture_git_dirty_paths: Callable[[Path], tuple[str, list[str]]],
    invoke_bridge: Callable[[str, str, dict[str, Any], int], dict[str, Any]],
    resolve_operation_default_timeout_ms: Callable[[Path, str, int], int],
    _decode_bridge_payload_dict: Callable[[dict[str, Any]], dict[str, Any] | None],
    write_json: Callable[[Path, dict[str, Any]], None],
    unavailable_workspace_side_effects: Callable[..., dict[str, Any]],
    build_workspace_side_effects: Callable[..., dict[str, Any]],
    run_artifact_probe: Callable[..., dict[str, Any]],
    truncate_text: Callable[[str, int], str],
    infer_gui_operation_succeeded: Callable[[dict[str, Any], dict[str, Any] | None], bool],
    build_batch_execution_summary: Callable[..., dict[str, Any]],
    attach_batch_lane_fields_to_summary: Callable[[dict[str, Any], dict[str, Any]], None],
    write_batch_summary_artifact: Callable[[Path, dict[str, Any]], None],
    batch_cli_output_payload: Callable[[dict[str, Any], str], dict[str, Any]],
    print_json: Callable[[Any], None],
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

    print_json(batch_cli_output_payload(payload, output_mode))
    if not bool(payload.get("succeeded")):
        raise SystemExit(1)


def ensure_batch_project_closed_data(
    project_root: Path,
    action_label: str,
    *,
    process_visibility_summary: Callable[[], dict[str, Any]],
    list_live_project_editor_pids: Callable[[Path], list[int]],
    build_batch_editor_conflict_details: Callable[[Path, list[int]], dict[str, Any]],
    ToolInvocationError: Any,
) -> None:
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


def run_batch_operation_data(
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
    progress_interval_seconds: float,
    progress_stdout: bool = True,
    batch_fallback_mode: str = "auto",
    refresh_license: bool = False,
    gui_operation: str = "",
    gui_operation_args: dict[str, Any] | None = None,
    artifact_probe_config: dict[str, Any] | None = None,
    artifact_probe_path_override: str = "",
    artifact_probe_warn_only: bool = False,
    last_known_output_path: str = "",
    output_mode: str = "full",
    normalize_batch_fallback_mode: Callable[[Any], str],
    print_json: Callable[[Any], None],
    batch_summary_artifact_path: Callable[[Path], Path],
    build_batch_run_id: Callable[[str, str], str],
    batch_progress_sidecar_path: Callable[[Path, str], Path],
    BatchProgressReporter: Any,
    batch_lane_preflight_blocker: Callable[..., tuple[str, dict[str, Any] | None]],
    run_gui_fallback_operation: Callable[..., None],
    ToolInvocationError: Any,
    build_batch_prepare_failure_summary: Callable[..., dict[str, Any]],
    truncate_text: Callable[[str, int], str],
    attach_batch_lane_fields_to_summary: Callable[[dict[str, Any], dict[str, Any]], None],
    write_batch_summary_artifact: Callable[[Path, dict[str, Any]], None],
    attach_batch_summary_to_error: Callable[..., Any],
    clear_stale_project_lock: Callable[[Path], dict[str, Any]],
    capture_git_dirty_paths: Callable[[Path], tuple[str, list[str]]],
    run_subprocess_with_progress: Callable[..., tuple[int, bool]],
    unavailable_workspace_side_effects: Callable[..., dict[str, Any]],
    build_workspace_side_effects: Callable[..., dict[str, Any]],
    try_read_json_dict: Callable[..., dict[str, Any] | None],
    read_json: Callable[..., Any],
    run_artifact_probe: Callable[..., dict[str, Any]],
    read_recent_editor_log: Callable[[Path, float], list[str]],
    build_batch_execution_summary: Callable[..., dict[str, Any]],
    batch_cli_output_payload: Callable[[dict[str, Any], str], dict[str, Any]],
    clear_stale_bridge_state: Callable[[Path], dict[str, Any]],
    time_time: Callable[[], float],
) -> None:
    if timeout_ms is not None and timeout_ms <= 0:
        timeout_ms = None
    payload["timeout_ms"] = timeout_ms
    payload["requested_execution_lane"] = "batch"
    payload["effective_execution_lane"] = "batch"
    payload["batch_fallback_mode"] = normalize_batch_fallback_mode(batch_fallback_mode)
    output_mode = "compact" if output_mode == "compact" else "full"

    if dry_run:
        print_json(batch_cli_output_payload(payload, output_mode))
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
                output_mode=output_mode,
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

    command_started_at = time_time()
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

    print_json(batch_cli_output_payload(payload, output_mode))
    if batch_exit_code != 0 or not bool(payload.get("succeeded")):
        raise SystemExit(1)
