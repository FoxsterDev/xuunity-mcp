from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from server_bridge_runtime import build_bridge_stabilization_summary


def truncate_text(value: Any, max_length: int = 240) -> str:
    text = str(value or "")
    if len(text) <= max_length:
        return text
    return text[: max(0, max_length - 3)] + "..."


UI_SMOKE_PAYLOAD_FIELDS = (
    "user_path",
    "selected_tab",
    "selected_screen",
    "before_model",
    "after_model",
    "before_ui",
    "after_ui",
    "blocking_popup",
    "failure_class",
    "screenshot_path",
)

SCENARIO_FAILURE_CLASSES = {
    "none",
    "product_assertion",
    "startup_lobby",
    "precondition",
    "blocking_popup",
    "infrastructure_timeout",
    "cleanup",
    "unity_unproven",
}

INFRASTRUCTURE_TIMEOUT_ERROR_CODES = {
    "project_refresh_timeout",
    "compile_player_scripts_timeout",
    "editor_idle_timeout",
    "unity_response_timeout",
    "bridge_timeout",
    "request_timeout",
    "scenario_wait_timeout",
}

EDITOR_RELAUNCH_ATTRIBUTION_FIELDS = (
    "editor_relaunched",
    "previous_editor_pid",
    "current_editor_pid",
    "bridge_generation_before",
    "bridge_generation_after",
    "cold_start_reason",
)


def normalize_scenario_payload(payload: dict[str, Any], scenario_terminal_statuses: set[str]) -> dict[str, Any]:
    normalized = dict(payload)
    status = str(normalized.get("status") or "")
    terminal = status in scenario_terminal_statuses
    normalized["terminal"] = terminal
    normalized["succeeded"] = status == "passed"
    normalized["terminal_status"] = status if terminal else ""
    normalized["terminal_statuses"] = sorted(scenario_terminal_statuses)
    return normalized


def utc_age_seconds(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, time.time() - parsed.timestamp())
    except Exception:
        return None


def build_status_summary(
    project_root: Path,
    payload: dict[str, Any],
    *,
    read_best_effort_bridge_state: Callable[[Path], dict[str, Any] | None],
    try_read_bridge_state: Callable[[Path], dict[str, Any] | None],
    pid_is_alive: Callable[[int], bool],
    heartbeat_age_seconds: Callable[[dict[str, Any]], float | None],
    derive_busy_reason: Callable[[dict[str, Any] | None], str],
    summarize_state_for_error: Callable[[dict[str, Any] | None], str],
    discovery_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = read_best_effort_bridge_state(project_root) or try_read_bridge_state(project_root) or {}
    effective = dict(state)
    effective.update(payload or {})

    editor_pid = int(effective.get("editor_pid") or 0)
    editor_running = bool(payload.get("editor_running", editor_pid > 0))
    if editor_pid > 0:
        editor_running = editor_running and pid_is_alive(editor_pid)

    heartbeat_age = heartbeat_age_seconds(effective)
    busy_reason = derive_busy_reason(effective)
    transport = str(effective.get("transport") or effective.get("transport_requested") or "")
    transport_listener_state = str(effective.get("transport_listener_state") or "")
    if transport == "file_ipc" and not transport_listener_state:
        transport_listener_state = "inactive"
    active_test_started_age = utc_age_seconds(effective.get("active_test_started_at_utc"))
    active_test_progress_age = utc_age_seconds(effective.get("active_test_last_progress_at_utc"))
    summary = {
        "action": "unity_status_summary",
        "project_root": str(project_root),
        "editor_running": editor_running,
        "editor_pid": editor_pid,
        "mcp_reachable": bool(payload.get("mcp_reachable", True)),
        "health_status": str(effective.get("health_status") or "unknown"),
        "transport": transport,
        "transport_listener_state": transport_listener_state,
        "bridge_generation": int(effective.get("bridge_generation") or 0),
        "bridge_session_id": str(effective.get("bridge_session_id") or ""),
        "playmode_state": str(effective.get("playmode_state") or ""),
        "script_compilation_failed": bool(effective.get("script_compilation_failed")),
        "compiler_error_count": int(effective.get("compiler_error_count") or 0),
        "recent_compiler_diagnostics": list(effective.get("recent_compiler_diagnostics") or [])[:5],
        "compiler_diagnostics_source": str(effective.get("compiler_diagnostics_source") or ""),
        "busy_reason": busy_reason,
        "busy_reason_detail": truncate_text(effective.get("busy_reason_detail") or ""),
        "pending_request_count": int(effective.get("pending_request_count") or 0),
        "active_operation": str(effective.get("active_operation") or ""),
        "active_test_request_id": str(effective.get("active_test_request_id") or ""),
        "active_test_operation": str(effective.get("active_test_operation") or ""),
        "active_test_run_phase": str(effective.get("active_test_run_phase") or ""),
        "active_test_started_at_utc": str(effective.get("active_test_started_at_utc") or ""),
        "active_test_last_started_test": truncate_text(effective.get("active_test_last_started_test") or ""),
        "active_test_last_finished_test": truncate_text(effective.get("active_test_last_finished_test") or ""),
        "active_test_last_progress_at_utc": str(effective.get("active_test_last_progress_at_utc") or ""),
        "active_test_last_progress_age_seconds": None if active_test_progress_age is None else round(active_test_progress_age, 3),
        "active_test_elapsed_runtime_seconds": None if active_test_started_age is None else round(active_test_started_age, 3),
        "active_test_runtime_timeout_ms": int(effective.get("active_test_runtime_timeout_ms") or 0),
        "last_completed_operation": str(effective.get("last_completed_operation") or ""),
        "last_completed_operation_status": str(effective.get("last_completed_operation_status") or ""),
        "last_completed_operation_duration_seconds": round(float(effective.get("last_completed_operation_duration_seconds") or 0.0), 3),
        "heartbeat_age_seconds": None if heartbeat_age is None else round(heartbeat_age, 3),
        "request_journal_head": str(effective.get("request_journal_head") or ""),
        "state_summary": summarize_state_for_error(effective),
    }
    for key in ("structured_timing", "artifact_manifest"):
        if key in payload:
            summary[key] = payload.get(key)
    discovery = dict(discovery_details or {})
    if discovery:
        summary.update(
            {
                "host_health_classification": str(discovery.get("host_health_classification") or ""),
                "host_health_reason": str(discovery.get("host_health_reason") or ""),
                "host_health_recommended_next_action": str(discovery.get("host_health_recommended_next_action") or ""),
                "host_health_termination_policy": str(discovery.get("host_health_termination_policy") or ""),
                "host_health_heartbeat_age_seconds": discovery.get("host_health_heartbeat_age_seconds"),
                "host_health_busy_reason": str(discovery.get("host_health_busy_reason") or ""),
                "host_health_progress_evidence": list(discovery.get("host_health_progress_evidence") or []),
                "anr_classification": str(discovery.get("anr_classification") or ""),
                "discovery_classification": str(discovery.get("discovery_classification") or ""),
                "discovery_reason": str(discovery.get("discovery_reason") or ""),
                "authoritative_state_source": str(discovery.get("authoritative_state_source") or ""),
                "reconciliation_case": str(discovery.get("reconciliation_case") or ""),
                "reconciliation_status": str(discovery.get("reconciliation_status") or ""),
                "reconciliation_reason": str(discovery.get("reconciliation_reason") or ""),
                "reconciliation_recommended_next_action": str(discovery.get("reconciliation_recommended_next_action") or ""),
                "detected_editor_count": int(discovery.get("detected_editor_count") or 0),
                "detected_editor_pids": list(discovery.get("detected_editor_pids") or []),
                "process_visibility_available": bool(discovery.get("process_visibility_available", True)),
                "process_visibility_error_code": str(discovery.get("process_visibility_error_code") or ""),
                "process_visibility_restricted": bool(discovery.get("process_visibility_restricted")),
                "editor_log_diagnosis": dict(discovery.get("editor_log_diagnosis") or {}),
                "editor_log_scope": dict(discovery.get("editor_log_scope") or {}),
                "stale_request_artifacts": dict(discovery.get("stale_request_artifacts") or {}),
                "host_prerequisites": dict(discovery.get("host_prerequisites") or {}),
                "transport_state": dict(discovery.get("transport_state") or {}),
                "state_groups": dict(discovery.get("state_groups") or {}),
            }
        )
    summary.update(
        build_bridge_stabilization_summary(
            effective,
            editor_running=editor_running,
            mcp_reachable=bool(payload.get("mcp_reachable", True)),
        )
    )
    return summary


__all__ = [name for name in globals() if not name.startswith("__")]
