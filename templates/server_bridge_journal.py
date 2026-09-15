#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from server_core import parse_utc_timestamp, read_json, write_json
from server_bridge_paths import request_journal_dir

HOST_CLIENT_KIND_MCP_SERVER = "mcp_server"
HOST_CLIENT_KIND_CLI = "cli"
HOST_CLIENT_SESSION_STARTED_UNIX = time.time()
_CONFIGURED_CLIENT_SESSION_ID = str(os.environ.get("XUUNITY_CLIENT_SESSION_ID") or "").strip()
HOST_CLIENT_SESSION_ID = _CONFIGURED_CLIENT_SESSION_ID or uuid.uuid4().hex
os.environ["XUUNITY_CLIENT_SESSION_ID"] = HOST_CLIENT_SESSION_ID
_CONFIGURED_CLIENT_KIND = str(os.environ.get("XUUNITY_CLIENT_KIND") or "").strip().lower()
_HOST_CLIENT_KIND = _CONFIGURED_CLIENT_KIND or HOST_CLIENT_KIND_MCP_SERVER


def current_client_session_id() -> str:
    return HOST_CLIENT_SESSION_ID


def current_client_kind() -> str:
    return _HOST_CLIENT_KIND


def mark_host_client_kind(kind: str) -> None:
    global _HOST_CLIENT_KIND
    if _CONFIGURED_CLIENT_KIND:
        return
    normalized = str(kind or "").strip().lower()
    if normalized:
        _HOST_CLIENT_KIND = normalized


def _json_only_enabled() -> bool:
    return str(os.environ.get("XUUNITY_JSON_ONLY") or "").strip().lower() in {"1", "true", "yes"}

def bridge_identity_from_state(state: dict[str, Any] | None) -> tuple[int, str]:
    if not state:
        return 0, ""

    generation = int(state.get("bridge_generation") or 0)
    session_id = str(state.get("bridge_session_id") or "")
    return generation, session_id


def emit_request_submission_ack(
    *,
    project_root: Path,
    operation: str,
    request_id: str,
    transport_name: str,
    state: dict[str, Any] | None,
) -> None:
    if _json_only_enabled():
        return
    bridge_generation, bridge_session_id = bridge_identity_from_state(state)
    message = (
        "[xuunity-mcp] request_submitted "
        f"operation={operation} "
        f"request_id={request_id} "
        f"transport={transport_name} "
        f"bridge_generation={bridge_generation} "
        f"bridge_session_id={bridge_session_id or '-'} "
        f"project_root={project_root}\n"
    )
    try:
        sys.stderr.write(message)
        sys.stderr.flush()
    except Exception:
        pass


def emit_request_not_submitted_ack(
    *,
    project_root: Path,
    operation: str,
    transport_name: str,
    reason: str,
) -> None:
    if _json_only_enabled():
        return
    message = (
        "[xuunity-mcp] request_not_submitted "
        f"operation={operation} "
        f"transport={transport_name} "
        f"reason={reason} "
        f"project_root={project_root}\n"
    )
    try:
        sys.stderr.write(message)
        sys.stderr.flush()
    except Exception:
        pass


def emit_operation_progress_phase(
    *,
    project_root: Path,
    operation: str,
    phase: str,
    request_id: str = "",
    state: dict[str, Any] | None = None,
    detail: str = "",
) -> None:
    if _json_only_enabled():
        return
    bridge_generation, bridge_session_id = bridge_identity_from_state(state)
    busy_reason = str((state or {}).get("busy_reason") or "")
    message = (
        "[xuunity-mcp] operation_progress "
        f"operation={operation} "
        f"phase={phase} "
        f"request_id={request_id or '-'} "
        f"bridge_generation={bridge_generation} "
        f"bridge_session_id={bridge_session_id or '-'} "
        f"busy_reason={busy_reason or '-'} "
        f"project_root={project_root}"
    )
    if detail:
        message += f" detail={detail}"
    try:
        sys.stderr.write(message + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def record_request_refused_event(project_root: Path, operation: str, error: Any, state: dict[str, Any] | None) -> Path:
    from server_recovery_commands import recommended_recovery_command_for_project

    details = dict(error.details or {})
    next_action = str(details.get("recommended_next_action") or "")
    effective = state or {}
    return write_host_request_journal_event(project_root, "request_refused", {
        "request_id": "",
        "request_submitted": False,
        "operation": operation,
        "code": error.code,
        "reason": error.message,
        "recommended_next_action": next_action,
        "recommended_recovery_command": details.get("recommended_recovery_command") or recommended_recovery_command_for_project(project_root, next_action),
        "state_fingerprint": {key: effective.get(key) for key in (
            "editor_pid", "bridge_generation", "bridge_session_id", "heartbeat_utc", "busy_reason",
            "busy_reason_detail", "compiler_diagnostics_captured_utc", "compiler_diagnostics_bridge_generation",
            "script_compilation_failed", "compiler_error_count",
        )},
        "details": details,
    })


def record_operation_progress_event(
    *,
    project_root: Path,
    operation: str,
    phase: str,
    request_id: str = "",
    state: dict[str, Any] | None = None,
    detail: str = "",
) -> Path:
    bridge_generation, bridge_session_id = bridge_identity_from_state(state)
    return write_host_request_journal_event(
        project_root,
        "operation_progress",
        {
            "request_id": request_id,
            "operation": operation,
            "phase": phase,
            "detail": detail,
            "bridge_generation": bridge_generation,
            "bridge_session_id": bridge_session_id,
            "busy_reason": str((state or {}).get("busy_reason") or ""),
            "progress_event": True,
        },
    )


def report_operation_progress_phase(
    *,
    project_root: Path,
    operation: str,
    phase: str,
    request_id: str = "",
    state: dict[str, Any] | None = None,
    detail: str = "",
) -> None:
    emit_operation_progress_phase(
        project_root=project_root,
        operation=operation,
        phase=phase,
        request_id=request_id,
        state=state,
        detail=detail,
    )
    try:
        record_operation_progress_event(
            project_root=project_root,
            operation=operation,
            phase=phase,
            request_id=request_id,
            state=state,
            detail=detail,
        )
    except Exception:
        pass


def record_request_submission_event(
    *,
    project_root: Path,
    request_id: str,
    operation: str,
    transport_name: str,
    state: dict[str, Any] | None,
    timeout_ms: int = 0,
) -> Path:
    bridge_generation, bridge_session_id = bridge_identity_from_state(state)
    return write_host_request_journal_event(
        project_root,
        "request_submitted",
        {
            "request_id": request_id,
            "operation": operation,
            "transport": transport_name,
            "bridge_generation": bridge_generation,
            "bridge_session_id": bridge_session_id,
            "request_submitted": True,
            "request_ownership_acquired": False,
            "host_delivery_tracking": True,
            "request_timeout_ms": max(0, int(timeout_ms or 0)),
            "request_submitted_unix": time.time(),
        },
    )


def record_request_delivery_event(
    *,
    project_root: Path,
    request_id: str,
    operation: str,
    transport_name: str,
    state: dict[str, Any] | None,
    observed: bool,
    source: str,
    reason: str = "",
) -> Path:
    bridge_generation, bridge_session_id = bridge_identity_from_state(state)
    return write_host_request_journal_event(
        project_root,
        "request_delivery_observed" if observed else "request_delivery_unproven",
        {
            "request_id": request_id,
            "operation": operation,
            "transport": transport_name,
            "bridge_generation": bridge_generation,
            "bridge_session_id": bridge_session_id,
            "host_delivery_observed": observed,
            "host_delivery_source": source,
            "reason": reason,
        },
    )


def bridge_identity_changed(
    initial_generation: int,
    initial_session_id: str,
    state: dict[str, Any] | None,
) -> bool:
    current_generation, current_session_id = bridge_identity_from_state(state)
    if current_generation <= 0 and not current_session_id:
        return False

    if initial_generation > 0 and current_generation != initial_generation:
        return True

    if initial_session_id and current_session_id and current_session_id != initial_session_id:
        return True

    return False

def write_host_request_journal_event(
    project_root: Path,
    event_type: str,
    payload: dict[str, Any],
) -> Path:
    journal_dir = request_journal_dir(project_root)
    journal_dir.mkdir(parents=True, exist_ok=True)
    compact_utc = time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + f"{int((time.time() % 1) * 1000):03d}Z"
    event_id = f"{compact_utc}_{uuid.uuid4().hex}_{event_type}"
    path = journal_dir / f"{event_id}.json"
    data = dict(payload)
    data.setdefault("event_id", event_id)
    data.setdefault("event_type", event_type)
    data.setdefault("event_source", "host_wrapper")
    data.setdefault("client_session_id", HOST_CLIENT_SESSION_ID)
    if str(data.get("client_session_id") or "") == HOST_CLIENT_SESSION_ID:
        data.setdefault("client_kind", current_client_kind())
    data.setdefault("event_at_utc", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    data.setdefault("project_root", str(project_root))
    write_json(path, data)
    return path


def summarize_request_attribution(project_root: Path) -> dict[str, Any]:
    """Summarize request initiators observed since this host process started."""

    own = 0
    foreign = 0
    cli = 0
    unattributed = 0
    last_foreign_at_utc = ""
    last_cli_at_utc = ""
    journal_dir = request_journal_dir(project_root)
    if journal_dir.is_dir():
        for path in journal_dir.glob("*.json"):
            try:
                event = read_json(path)
            except Exception:
                continue
            if not isinstance(event, dict) or str(event.get("event_type") or "") != "request_submitted":
                continue
            try:
                submitted_unix = float(event.get("request_submitted_unix") or 0.0)
            except (TypeError, ValueError):
                submitted_unix = 0.0
            if submitted_unix <= 0.0:
                submitted_unix = parse_journal_utc_timestamp(event.get("event_at_utc"))
            if submitted_unix + 0.001 < HOST_CLIENT_SESSION_STARTED_UNIX:
                continue
            client_session_id = str(event.get("client_session_id") or "").strip()
            if not client_session_id:
                unattributed += 1
                continue
            if client_session_id == HOST_CLIENT_SESSION_ID:
                own += 1
                continue
            stamp = str(event.get("event_at_utc") or "")
            if str(event.get("client_kind") or "").strip().lower() == HOST_CLIENT_KIND_CLI:
                cli += 1
                if stamp > last_cli_at_utc:
                    last_cli_at_utc = stamp
                continue
            foreign += 1
            if stamp > last_foreign_at_utc:
                last_foreign_at_utc = stamp

    return {
        "client_session_id": HOST_CLIENT_SESSION_ID,
        "client_kind": current_client_kind(),
        "client_session_started_unix": HOST_CLIENT_SESSION_STARTED_UNIX,
        "own_requests_since_client_start": own,
        "foreign_requests_since_client_start": foreign,
        "cli_requests_since_client_start": cli,
        "unattributed_requests_since_client_start": unattributed,
        "foreign_request_activity_detected": foreign > 0,
        "cli_request_activity_detected": cli > 0,
        "last_foreign_request_at_utc": last_foreign_at_utc,
        "last_cli_request_at_utc": last_cli_at_utc,
    }


def parse_journal_utc_timestamp(value: Any) -> float:
    return parse_utc_timestamp(value) or 0.0


def read_request_journal_events(project_root: Path, request_id: str) -> list[dict[str, Any]]:
    journal_dir = request_journal_dir(project_root)
    if not journal_dir.is_dir():
        return []

    matched: list[dict[str, Any]] = []
    for path in journal_dir.glob("*.json"):
        try:
            payload = read_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("request_id") or "") != request_id:
            continue

        event = dict(payload)
        event["_path"] = str(path)
        matched.append(event)

    matched.sort(
        key=lambda item: (
            parse_journal_utc_timestamp(item.get("event_at_utc")),
            str(item.get("event_id") or ""),
        )
    )
    return matched
