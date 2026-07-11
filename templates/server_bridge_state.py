#!/usr/bin/env python3
from __future__ import annotations

import calendar
import time
from pathlib import Path
from typing import Any

from server_bridge_constants import (
    DEFAULT_BRIDGE_TRANSPORT,
    DEFAULT_IDLE_STABLE_CYCLES,
    TCP_LOOPBACK_BRIDGE_TRANSPORT,
)
from server_bridge_paths import bridge_config_path, bridge_state_path
from server_core import ToolInvocationError, read_json, render_launcher_cli
from server_host_platform import current_host_platform_adapter

def bridge_enabled(project_root: Path) -> bool:
    config_path = bridge_config_path(project_root)
    if not config_path.is_file():
        return False

    try:
        data = read_json(config_path)
    except Exception:
        return False

    return bool(data.get("enabled"))


def try_read_bridge_config(project_root: Path) -> dict[str, Any] | None:
    config_path = bridge_config_path(project_root)
    if not config_path.is_file():
        return None

    try:
        data = read_json(config_path)
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def try_read_bridge_state(project_root: Path) -> dict[str, Any] | None:
    path = bridge_state_path(project_root)
    if not path.is_file():
        return None

    try:
        data = read_json(path)
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def pid_is_alive(pid: int) -> bool:
    return current_host_platform_adapter().pid_is_alive(pid)


def try_read_live_editor_state(project_root: Path) -> dict[str, Any] | None:
    state = try_read_bridge_state(project_root)
    if not state:
        return None

    pid = int(state.get("editor_pid") or 0)
    if not pid_is_alive(pid):
        return None

    return state


def read_best_effort_bridge_state(project_root: Path) -> dict[str, Any] | None:
    live_state = try_read_live_editor_state(project_root)
    if live_state is not None:
        return live_state

    state = try_read_bridge_state(project_root)
    if state is None:
        return None

    pid = int(state.get("editor_pid") or 0)
    if pid > 0 and not pid_is_alive(pid):
        return None

    return state

def heartbeat_age_seconds(state: dict[str, Any]) -> float | None:
    heartbeat_utc = state.get("heartbeat_utc")
    if not isinstance(heartbeat_utc, str) or not heartbeat_utc:
        return None

    try:
        heartbeat_unix = calendar.timegm(time.strptime(heartbeat_utc, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return None

    return max(0.0, time.time() - heartbeat_unix)


def inspect_bridge_state_liveness(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {
            "state_present": False,
            "state_is_live": False,
            "editor_pid": 0,
            "editor_pid_alive": False,
            "heartbeat_age_seconds": None,
            "stale_reason": "state_missing",
        }

    pid = int(state.get("editor_pid") or 0)
    pid_alive = pid > 0 and pid_is_alive(pid)
    heartbeat_age = heartbeat_age_seconds(state)
    stale_reason = ""

    if pid <= 0:
        stale_reason = "missing_editor_pid"
    elif not pid_alive:
        stale_reason = "editor_pid_not_alive"

    return {
        "state_present": True,
        "state_is_live": pid_alive,
        "editor_pid": pid,
        "editor_pid_alive": pid_alive,
        "heartbeat_age_seconds": round(heartbeat_age, 3) if heartbeat_age is not None else None,
        "stale_reason": stale_reason,
    }


def annotate_bridge_state_with_liveness(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not state:
        return None

    annotated = dict(state)
    annotated["_xuunity_bridge_state"] = inspect_bridge_state_liveness(state)
    return annotated


def parse_utc_timestamp(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None

    try:
        return float(calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ")))
    except ValueError:
        return None


def state_is_idle(state: dict[str, Any]) -> bool:
    return (
        not bool(state.get("domain_reload_in_progress"))
        and not bool(state.get("package_operation_in_progress"))
        and not bool(state.get("script_reload_pending"))
        and not bool(state.get("asset_import_in_progress"))
        and not bool(state.get("refresh_settle_pending"))
        and not bool(state.get("compile_settle_pending"))
        and not bool(state.get("playmode_transition_pending"))
        and not bool(state.get("is_compiling"))
        and not bool(state.get("is_updating"))
        and not bool(state.get("active_operation"))
        and (bool(state.get("is_playing")) or not bool(state.get("is_playing_or_will_change_playmode")))
    )


def idle_wait_blocking_reasons(
    state: dict[str, Any] | None,
    *,
    heartbeat_max_age_seconds: int,
    require_healthy_bridge: bool,
    after_request_id: str | None = None,
    not_before_unix: float | None = None,
) -> list[str]:
    if not state:
        return ["bridge_state_missing"]

    reasons: list[str] = []
    age_seconds = heartbeat_age_seconds(state)
    if age_seconds is None:
        reasons.append("heartbeat_missing")
    elif age_seconds > heartbeat_max_age_seconds:
        reasons.append("heartbeat_stale")

    if require_healthy_bridge and state.get("health_status") != "healthy":
        reasons.append("health_not_healthy")

    last_processed_request_id = str(state.get("last_processed_request_id") or "")
    last_pump_unix = parse_utc_timestamp(state.get("last_pump_utc"))
    request_match = (
        after_request_id is None
        or last_processed_request_id == after_request_id
        or (
            not_before_unix is not None
            and last_pump_unix is not None
            and last_pump_unix >= not_before_unix
        )
    )
    if not request_match:
        reasons.append("after_request_not_observed")

    if bool(state.get("domain_reload_in_progress")):
        reasons.append("domain_reload_in_progress")
    if bool(state.get("package_operation_in_progress")):
        reasons.append("package_operation_in_progress")
    if bool(state.get("refresh_settle_pending")):
        reasons.append("refresh_settle_pending")
    if bool(state.get("compile_settle_pending")):
        reasons.append("compile_settle_pending")
    if bool(state.get("playmode_transition_pending")):
        reasons.append("playmode_transition_pending")
    if bool(state.get("is_compiling")):
        reasons.append("is_compiling")
    if bool(state.get("script_reload_pending")):
        reasons.append("script_reload_pending")
    if bool(state.get("asset_import_in_progress")):
        reasons.append("asset_import_in_progress")
    if bool(state.get("is_updating")):
        reasons.append("is_updating")
    if str(state.get("active_operation") or ""):
        reasons.append("active_operation")
    if (
        not bool(state.get("is_playing"))
        and bool(state.get("is_playing_or_will_change_playmode"))
    ):
        reasons.append("playmode_transition")
    if int(state.get("pending_request_count") or 0) > 0:
        reasons.append("pending_request_in_flight")
    if not state_is_idle(state) and not reasons:
        reasons.append("editor_not_idle")

    deduped: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        deduped.append(reason)
    return deduped


def build_editor_idle_timeout_details(
    project_root: Path,
    *,
    last_state: dict[str, Any] | None,
    reason: str,
    timeout_ms: int,
    heartbeat_max_age_seconds: int,
    require_healthy_bridge: bool,
    after_request_id: str | None = None,
    not_before_unix: float | None = None,
    elapsed_seconds: float = 0.0,
) -> dict[str, Any]:
    age_seconds = heartbeat_age_seconds(last_state) if last_state else None
    blocking_reasons = idle_wait_blocking_reasons(
        last_state,
        heartbeat_max_age_seconds=heartbeat_max_age_seconds,
        require_healthy_bridge=require_healthy_bridge,
        after_request_id=after_request_id,
        not_before_unix=not_before_unix,
    )
    return {
        "classification": "editor_idle_timeout",
        "result_trust_class": "editor_state_not_idle",
        "heartbeat_age_seconds": None if age_seconds is None else round(age_seconds, 3),
        "busy_reason": derive_busy_reason(last_state),
        "blocking_reasons": blocking_reasons,
        "safe_to_retry": False,
        "recommended_next_action": "wait_for_editor_idle_or_inspect_busy_state",
        "recommended_recovery_command": render_launcher_cli(
            "request-status-summary", project_root, "--include-full-payload"
        ),
        "request_id": str(after_request_id or ""),
        "operation": str(reason or ""),
        "idle_wait_reason": str(reason or ""),
        "timeout_ms": int(timeout_ms or 0),
        "elapsed_seconds": round(max(0.0, float(elapsed_seconds or 0.0)), 3),
        "full_payload_available": True,
        "full_payload_recovery_command": render_launcher_cli(
            "request-status-summary", project_root, "--include-full-payload"
        ),
        "full_payload_tool_arguments": {"includeFullPayload": True},
    }


def derive_busy_reason(state: dict[str, Any] | None) -> str:
    if not state:
        return "bridge_state_missing"

    busy_reason = state.get("busy_reason")
    if isinstance(busy_reason, str) and busy_reason:
        return busy_reason

    if bool(state.get("domain_reload_in_progress")):
        return "domain_reload"

    if bool(state.get("package_operation_in_progress")):
        return "package_operation"

    if bool(state.get("refresh_settle_pending")):
        return "refresh_settle"

    if bool(state.get("compile_settle_pending")):
        return "compile_settle"

    if bool(state.get("playmode_transition_pending")):
        return "playmode_settle"

    if bool(state.get("is_compiling")):
        return "compiling"

    if bool(state.get("script_reload_pending")):
        return "script_reload_pending"

    if bool(state.get("asset_import_in_progress")):
        return "asset_import"

    if bool(state.get("is_updating")):
        return "updating"

    if state.get("active_operation"):
        return "processing_request"

    if not bool(state.get("is_playing")) and bool(state.get("is_playing_or_will_change_playmode")):
        return "playmode_transition"

    if int(state.get("pending_request_count") or 0) > 0:
        return "request_queue_pending"

    return "idle"


def summarize_state_for_error(state: dict[str, Any] | None) -> str:
    if not state:
        return "No live bridge state was available."

    heartbeat_age = heartbeat_age_seconds(state)
    heartbeat_summary = "unknown"
    if heartbeat_age is not None:
        heartbeat_summary = f"{round(heartbeat_age, 3)}s"

    return (
        f"bridge_version={state.get('bridge_version') or 'unknown'}, "
        f"bridge_generation={state.get('bridge_generation') or 'unknown'}, "
        f"bridge_session_id={state.get('bridge_session_id') or ''}, "
        f"busy_reason={derive_busy_reason(state)}, "
        f"heartbeat_age={heartbeat_summary}, "
        f"domain_reload_in_progress={bool(state.get('domain_reload_in_progress'))}, "
        f"package_operation_in_progress={bool(state.get('package_operation_in_progress'))}, "
        f"package_operation_name={state.get('package_operation_name') or ''}, "
        f"package_operation_phase={state.get('package_operation_phase') or ''}, "
        f"refresh_settle_pending={bool(state.get('refresh_settle_pending'))}, "
        f"refresh_settle_phase={state.get('refresh_settle_phase') or ''}, "
        f"compile_settle_pending={bool(state.get('compile_settle_pending'))}, "
        f"compile_settle_phase={state.get('compile_settle_phase') or ''}, "
        f"playmode_transition_pending={bool(state.get('playmode_transition_pending'))}, "
        f"playmode_transition_phase={state.get('playmode_transition_phase') or ''}, "
        f"playmode_transition_target_state={state.get('playmode_transition_target_state') or ''}, "
        f"script_reload_pending={bool(state.get('script_reload_pending'))}, "
        f"asset_import_in_progress={bool(state.get('asset_import_in_progress'))}, "
        f"is_compiling={bool(state.get('is_compiling'))}, "
        f"is_updating={bool(state.get('is_updating'))}, "
        f"is_playing={bool(state.get('is_playing'))}, "
        f"is_playing_or_will_change_playmode={bool(state.get('is_playing_or_will_change_playmode'))}, "
        f"health_status={state.get('health_status') or 'unknown'}, "
        f"active_operation={state.get('active_operation') or ''}, "
        f"busy_reason_detail={state.get('busy_reason_detail') or ''}, "
        f"last_processed_request_id={state.get('last_processed_request_id') or ''}, "
        f"request_journal_head={state.get('request_journal_head') or ''}, "
        f"pending_request_count={int(state.get('pending_request_count') or 0)}"
    )


def wait_for_editor_idle(
    project_root: Path,
    timeout_ms: int,
    heartbeat_max_age_seconds: int,
    reason: str,
    *,
    after_request_id: str | None = None,
    not_before_unix: float | None = None,
    require_healthy_bridge: bool = True,
    stable_cycles: int = DEFAULT_IDLE_STABLE_CYCLES,
) -> dict[str, Any]:
    started_at = time.time()
    deadline = started_at + (timeout_ms / 1000.0)
    stable_matches = 0
    last_state: dict[str, Any] | None = None

    while time.time() < deadline:
        state = try_read_live_editor_state(project_root)
        if state:
            last_state = state
            age_seconds = heartbeat_age_seconds(state)
            heartbeat_is_fresh = age_seconds is not None and age_seconds <= heartbeat_max_age_seconds
            bridge_is_healthy = not require_healthy_bridge or state.get("health_status") == "healthy"
            last_processed_request_id = str(state.get("last_processed_request_id") or "")
            last_pump_unix = parse_utc_timestamp(state.get("last_pump_utc"))
            request_match = (
                after_request_id is None
                or last_processed_request_id == after_request_id
                or (not_before_unix is not None and last_pump_unix is not None and last_pump_unix >= not_before_unix)
            )
            editor_is_idle = state_is_idle(state)

            if heartbeat_is_fresh and bridge_is_healthy and request_match and editor_is_idle:
                stable_matches += 1
                if stable_matches >= max(1, stable_cycles):
                    result = dict(state)
                    result["heartbeat_age_seconds"] = round(age_seconds or 0.0, 3)
                    result["idle_wait_reason"] = reason
                    result["idle_wait_duration_seconds"] = round(time.time() - started_at, 3)
                    return result
            else:
                stable_matches = 0
        else:
            stable_matches = 0

        time.sleep(0.5)

    request_summary = ""
    if after_request_id:
        request_summary = f" request_id={after_request_id}."

    details = build_editor_idle_timeout_details(
        project_root,
        last_state=last_state,
        reason=reason,
        timeout_ms=timeout_ms,
        heartbeat_max_age_seconds=heartbeat_max_age_seconds,
        require_healthy_bridge=require_healthy_bridge,
        after_request_id=after_request_id,
        not_before_unix=not_before_unix,
        elapsed_seconds=time.time() - started_at,
    )
    heartbeat_summary = (
        "unknown"
        if details["heartbeat_age_seconds"] is None
        else f"{details['heartbeat_age_seconds']}s"
    )
    blocking_summary = ",".join(str(item) for item in details.get("blocking_reasons") or []) or "none"
    raise ToolInvocationError(
        "editor_idle_timeout",
        (
            f"Timed out waiting for Unity editor idle ({reason})."
            f"{request_summary} busy_reason={details['busy_reason']} "
            f"heartbeat_age={heartbeat_summary} blocking_reasons={blocking_summary} "
            f"recommended_next_action={details['recommended_next_action']}"
        ),
        details,
    )


def wait_for_playmode_state(
    project_root: Path,
    timeout_ms: int,
    heartbeat_max_age_seconds: int,
    expected_state: str,
    reason: str,
    *,
    after_request_id: str | None = None,
    not_before_unix: float | None = None,
    stable_cycles: int = DEFAULT_IDLE_STABLE_CYCLES,
) -> dict[str, Any]:
    started_at = time.time()
    deadline = started_at + (timeout_ms / 1000.0)
    stable_matches = 0
    last_state: dict[str, Any] | None = None

    while time.time() < deadline:
        state = try_read_live_editor_state(project_root)
        if state:
            last_state = state
            age_seconds = heartbeat_age_seconds(state)
            heartbeat_is_fresh = age_seconds is not None and age_seconds <= heartbeat_max_age_seconds
            request_match = (
                after_request_id is None
                or str(state.get("last_processed_request_id") or "") == after_request_id
                or (
                    not_before_unix is not None
                    and parse_utc_timestamp(state.get("last_pump_utc")) is not None
                    and parse_utc_timestamp(state.get("last_pump_utc")) >= not_before_unix
                )
            )
            playmode_state = str(state.get("playmode_state") or "")
            transition_request_id = str(state.get("playmode_transition_request_id") or "")
            transition_phase = str(state.get("playmode_transition_phase") or "")
            transition_contract_applies = after_request_id is not None and transition_request_id == after_request_id
            transition_settled = (not transition_contract_applies) or transition_phase == "settled"

            if heartbeat_is_fresh and request_match and playmode_state == expected_state and transition_settled:
                stable_matches += 1
                if stable_matches >= max(1, stable_cycles):
                    result = dict(state)
                    result["heartbeat_age_seconds"] = round(age_seconds or 0.0, 3)
                    result["playmode_wait_reason"] = reason
                    result["playmode_wait_duration_seconds"] = round(time.time() - started_at, 3)
                    return result
            else:
                stable_matches = 0
        else:
            stable_matches = 0

        time.sleep(0.5)

    request_summary = ""
    if after_request_id:
        request_summary = f" request_id={after_request_id}."

    raise ToolInvocationError(
        "playmode_state_timeout",
        (
            f"Timed out waiting for play mode state '{expected_state}' ({reason})."
            f"{request_summary} {summarize_state_for_error(last_state)}"
        ),
    )


def expected_playmode_state_for_action(action: str) -> str | None:
    normalized = (action or "").strip().lower()
    mapping = {
        "enter": "playing",
        "exit": "edit",
        "pause": "paused",
        "resume": "playing",
    }
    return mapping.get(normalized)
