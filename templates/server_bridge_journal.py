#!/usr/bin/env python3
from __future__ import annotations

import calendar
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from server_core import read_json, write_json
from server_bridge_paths import request_journal_dir

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
    data.setdefault("event_at_utc", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    data.setdefault("project_root", str(project_root))
    write_json(path, data)
    return path


def parse_journal_utc_timestamp(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0

    try:
        return float(calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ")))
    except ValueError:
        return 0.0


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
