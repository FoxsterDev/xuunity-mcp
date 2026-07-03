from __future__ import annotations

from pathlib import Path
from typing import Any


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _compact_bridge_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "bridge_version": _int_or_zero(state.get("bridge_version")),
        "bridge_generation": _int_or_zero(state.get("bridge_generation")),
        "bridge_session_id": str(state.get("bridge_session_id") or ""),
        "editor_pid": _int_or_zero(state.get("editor_pid")),
        "unity_version": str(state.get("unity_version") or ""),
        "health_status": str(state.get("health_status") or ""),
        "transport": str(state.get("transport") or state.get("transport_requested") or ""),
        "transport_listener_state": str(state.get("transport_listener_state") or ""),
        "playmode_state": str(state.get("playmode_state") or ""),
        "is_playing": bool(state.get("is_playing")),
        "is_compiling": bool(state.get("is_compiling")),
        "is_updating": bool(state.get("is_updating")),
        "compiler_error_count": _int_or_zero(state.get("compiler_error_count")),
        "script_compilation_failed": bool(state.get("script_compilation_failed")),
        "pending_request_count": _int_or_zero(state.get("pending_request_count")),
        "last_processed_request_id": str(state.get("last_processed_request_id") or ""),
        "last_completed_operation": str(state.get("last_completed_operation") or ""),
        "last_completed_operation_status": str(state.get("last_completed_operation_status") or ""),
        "heartbeat_utc": str(state.get("heartbeat_utc") or ""),
        "editor_log_path": str(state.get("editor_log_path") or ""),
    }


def _compact_import_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "import_state": str(state.get("import_state") or ""),
        "dependency_declared": bool(state.get("dependency_declared")),
        "lock_entry_present": bool(state.get("lock_entry_present")),
        "package_cache_present": bool(state.get("package_cache_present")),
        "bridge_state_present": bool(state.get("bridge_state_present")),
    }


def _compact_launch(payload: dict[str, Any]) -> dict[str, Any]:
    launch = dict(payload.get("launch") or {})
    if not launch:
        return {}
    return {
        "reused_existing_editor": bool(launch.get("reused_existing_editor")),
        "reused_via": str(launch.get("reused_via") or ""),
        "opened_by_host": bool(launch.get("opened_by_host")),
        "editor_pid": _int_or_zero(launch.get("editor_pid")),
        "unity_app": str(launch.get("unity_app") or ""),
        "editor_log_path": str(launch.get("editor_log_path") or ""),
    }


def _next_action_for_ready(bridge_state: dict[str, Any], discovery: dict[str, Any]) -> str:
    health = str(bridge_state.get("health_status") or "")
    compiler_errors = _int_or_zero(bridge_state.get("compiler_error_count"))
    playmode = str(bridge_state.get("playmode_state") or "")
    if health != "healthy":
        return str(discovery.get("host_health_recommended_next_action") or "request-status-summary")
    if compiler_errors > 0 or bool(bridge_state.get("script_compilation_failed")):
        return "fix_compile_errors"
    if playmode == "playing":
        return "exit_playmode_before_editing"
    return "none"


def build_ensure_ready_summary(
    project_root: Path,
    payload: dict[str, Any],
    *,
    include_full_payload: bool = False,
) -> dict[str, Any]:
    if include_full_payload:
        return payload

    bridge_state = dict(payload.get("bridge_state") or {})
    discovery = dict(payload.get("discovery_after_ready") or payload.get("discovery") or {})
    package_import_state = dict(payload.get("package_import_state") or {})
    package_before = dict(payload.get("package_import_state_before_ready") or {})
    health_status = str(bridge_state.get("health_status") or "unknown")
    playmode_state = str(bridge_state.get("playmode_state") or "")
    next_action = _next_action_for_ready(bridge_state, discovery)

    summary: dict[str, Any] = {
        "action": "ensure_ready",
        "project_root": str(project_root),
        "payload_mode": "compact_ensure_ready",
        "full_payload_available": True,
        "full_payload_cli_args": [
            "ensure-ready",
            "--project-root",
            str(project_root),
            "--include-full-payload",
        ],
        "full_payload_command": (
            f"xuunity_light_unity_mcp.sh ensure-ready --project-root {project_root} --include-full-payload"
        ),
        "verdict": "ready" if health_status == "healthy" else "degraded",
        "succeeded": health_status == "healthy",
        "health": {
            "status": health_status,
            "compiler_error_count": _int_or_zero(bridge_state.get("compiler_error_count")),
            "script_compilation_failed": bool(bridge_state.get("script_compilation_failed")),
            "playmode_state": playmode_state,
            "pending_request_count": _int_or_zero(bridge_state.get("pending_request_count")),
            "busy_reason": str(bridge_state.get("busy_reason") or ""),
        },
        "bridge": {
            "generation": _int_or_zero(bridge_state.get("bridge_generation")),
            "session_id": str(bridge_state.get("bridge_session_id") or ""),
            "editor_pid": _int_or_zero(bridge_state.get("editor_pid")),
            "unity_version": str(bridge_state.get("unity_version") or ""),
            "transport": str(bridge_state.get("transport") or bridge_state.get("transport_requested") or ""),
            "transport_listener_state": str(bridge_state.get("transport_listener_state") or ""),
            "heartbeat_utc": str(bridge_state.get("heartbeat_utc") or ""),
        },
        "bridge_state": _compact_bridge_state(bridge_state),
        "package_import_state": _compact_import_state(package_import_state),
        "package_import_state_before_ready": _compact_import_state(package_before),
        "recommended_next_action": next_action,
        "recovery_command": "",
        "full_payload_recovery_args": [
            "ensure-ready",
            "--project-root",
            str(project_root),
            "--open-editor",
            "--include-full-payload",
        ],
        "full_payload_recovery_command": (
            f"xuunity_light_unity_mcp.sh ensure-ready --project-root {project_root} "
            "--open-editor --include-full-payload"
        ),
    }

    launch = _compact_launch(payload)
    if launch:
        summary["launch"] = launch

    editor_log_identity = dict(discovery.get("editor_log_identity") or {})
    if editor_log_identity:
        summary["editor_log_identity"] = editor_log_identity
        summary["editor_log_path"] = str(editor_log_identity.get("active_editor_log_path") or payload.get("editor_log_path") or "")
    else:
        summary["editor_log_path"] = str(payload.get("editor_log_path") or bridge_state.get("editor_log_path") or "")

    if next_action == "exit_playmode_before_editing":
        summary["playmode_hint"] = {
            "state": playmode_state,
            "message": "Editor is currently in Play Mode; exit Play Mode before edit/build work.",
            "command": f"xuunity_light_unity_mcp.sh request-playmode-set --project-root {project_root} --action exit",
        }
    elif playmode_state == "playing":
        summary["playmode_hint"] = {
            "state": playmode_state,
            "message": "Editor is currently in Play Mode.",
            "command": f"xuunity_light_unity_mcp.sh request-playmode-set --project-root {project_root} --action exit",
        }

    if next_action and next_action != "none":
        if next_action == "exit_playmode_before_editing":
            summary["recovery_command"] = summary["playmode_hint"]["command"]
        else:
            summary["recovery_command"] = (
                f"xuunity_light_unity_mcp.sh ensure-ready --project-root {project_root} --open-editor"
            )

    return summary


__all__ = [name for name in globals() if not name.startswith("__")]
