#!/usr/bin/env python3
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from server_bridge_constants import DEFAULT_BRIDGE_TRANSPORT
from server_bridge_final_status import build_bridge_stabilization_summary
from server_bridge_journal import read_request_journal_events, write_host_request_journal_event
from server_bridge_paths import inbox_dir, outbox_dir
from server_bridge_state import read_best_effort_bridge_state, try_read_bridge_state
from server_core import ToolInvocationError

def inbox_request_path(project_root: Path, request_id: str) -> Path:
    return inbox_dir(project_root) / f"{request_id}.json"


def cancel_request_best_effort(
    project_root: Path,
    request_id: str,
    *,
    operation: str = "",
    current_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    effective_state = current_state or read_best_effort_bridge_state(project_root) or try_read_bridge_state(project_root) or {}
    events = read_request_journal_events(project_root, request_id)
    if not events:
        raise ToolInvocationError(
            "request_not_found",
            f"No request journal events were found for request_id={request_id}.",
            {
                "request_id": request_id,
                "request_submitted": False,
                "request_ownership_acquired": False,
                "transport_outcome": "request_not_found",
                "operation_outcome": "request_unknown",
                "recommended_next_action": "request_status_summary_then_retry",
            },
        )

    submitted_events = [event for event in events if str(event.get("event_type") or "") == "request_submitted"]
    submitted_event = submitted_events[-1] if submitted_events else None
    started_event = next((event for event in events if str(event.get("event_type") or "") == "request_started"), None)
    completed_events = [event for event in events if str(event.get("event_type") or "") == "request_completed"]
    completed_event = completed_events[-1] if completed_events else None
    cancellation_events = [
        event
        for event in events
        if str(event.get("event_type") or "") in {"request_cancelled", "request_cancel_requested"}
    ]
    cancellation_event = cancellation_events[-1] if cancellation_events else None
    request_started = started_event is not None
    request_completed = completed_event is not None
    request_submitted = submitted_event is not None
    request_ownership_acquired = request_started or request_completed
    effective_operation = str(
        (completed_event or started_event or submitted_event or {}).get("operation") or operation or ""
    )
    transport_name = str((submitted_event or {}).get("transport") or (effective_state or {}).get("transport") or "")
    stabilization = build_bridge_stabilization_summary(effective_state)
    request_path = inbox_request_path(project_root, request_id)
    request_file_exists = request_path.is_file()

    result: dict[str, Any] = {
        "action": "request_cancel",
        "project_root": str(project_root),
        "request_id": request_id,
        "operation": effective_operation,
        "transport": transport_name,
        "request_submitted": request_submitted,
        "request_started": request_started,
        "request_completed": request_completed,
        "request_ownership_acquired": request_ownership_acquired,
        "request_file_path": str(request_path),
        "request_file_present": request_file_exists,
        "bridge_stabilization": stabilization,
        "recommended_recovery_command": (
            f"request-final-status --project-root {project_root} --request-id {request_id}"
        ),
    }

    if cancellation_event is not None:
        result.update(
            {
                "cancellation_event_type": str(cancellation_event.get("event_type") or ""),
                "cancellation_status": str(
                    cancellation_event.get("cancellation_status")
                    or cancellation_event.get("reclassified_status")
                    or ""
                ),
                "cancellation_reason": str(cancellation_event.get("reason") or ""),
                "recommended_next_action": "request_final_status",
            }
        )
        return result

    if request_completed:
        result.update(
            {
                "cancellation_event_type": "",
                "cancellation_status": "request_already_completed",
                "cancellation_reason": "request_completed_before_cancellation",
                "recommended_next_action": "none",
            }
        )
        return result

    cancellation_event_type = "request_cancel_requested"
    cancellation_status = "cancellation_requested_in_flight"
    cancellation_reason = "host_requested_cancellation_after_submission"
    request_file_deleted = False

    if request_submitted and not request_started and transport_name == DEFAULT_BRIDGE_TRANSPORT and request_file_exists:
        try:
            request_path.unlink()
            request_file_deleted = True
            cancellation_event_type = "request_cancelled"
            cancellation_status = "cancelled_before_unity_start"
            cancellation_reason = "host_cancelled_file_ipc_request_before_unity_start"
        except OSError:
            cancellation_event_type = "request_cancel_requested"
            cancellation_status = "cancellation_requested_in_flight"
            cancellation_reason = "host_cancellation_unable_to_remove_pending_request_file"

    journal_path = write_host_request_journal_event(
        project_root,
        cancellation_event_type,
        {
            "request_id": request_id,
            "operation": effective_operation,
            "reason": cancellation_reason,
            "retryable": True,
            "cancellation_status": cancellation_status,
            "transport": transport_name,
            "request_submitted": request_submitted,
            "request_ownership_acquired": request_ownership_acquired,
        },
    )

    result.update(
        {
            "cancellation_event_type": cancellation_event_type,
            "cancellation_status": cancellation_status,
            "cancellation_reason": cancellation_reason,
            "request_file_deleted": request_file_deleted,
            "journal_event_path": str(journal_path),
            "recommended_next_action": (
                "retry_request"
                if cancellation_status == "cancelled_before_unity_start" and stabilization.get("safe_to_retry")
                else "wait_for_bridge_stabilization"
                if not stabilization.get("safe_to_retry")
                else "request_final_status"
            ),
        }
    )
    return result


def inspect_stale_request_artifacts(
    project_root: Path,
    *,
    current_state: dict[str, Any] | None = None,
    stale_age_seconds: int = 600,
    max_entries: int = 20,
) -> dict[str, Any]:
    effective_state = current_state or read_best_effort_bridge_state(project_root) or try_read_bridge_state(project_root) or {}
    stabilization = build_bridge_stabilization_summary(effective_state)
    pending_request_count = int(stabilization.get("pending_request_count") or 0)
    cutoff_unix = time.time() - max(1, int(stale_age_seconds))
    candidates: list[dict[str, Any]] = []
    classifications: dict[str, int] = {}
    candidate_paths: list[Path] = []

    def consider_path(path: Path, artifact_kind: str) -> None:
        try:
            stat_result = path.stat()
        except OSError:
            return

        if stat_result.st_mtime >= cutoff_unix:
            return

        request_id = str(path.stem or "").strip()
        if not request_id:
            return

        events = read_request_journal_events(project_root, request_id)
        event_types = {str(event.get("event_type") or "") for event in events}
        terminal_event_type = next(
            (
                str(event.get("event_type") or "")
                for event in reversed(events)
                if str(event.get("event_type") or "") in {
                    "request_completed",
                    "request_abandoned",
                    "request_reclassified",
                    "request_cancelled",
                }
            ),
            "",
        )
        request_started = "request_started" in event_types
        request_submitted = "request_submitted" in event_types
        age_seconds = max(0.0, time.time() - stat_result.st_mtime)

        classification = ""
        cleanup_candidate = False
        if artifact_kind == "inbox":
            if terminal_event_type:
                classification = "stale_inbox_after_terminal_event"
                cleanup_candidate = True
            elif request_submitted and not request_started and stabilization.get("safe_to_retry") and pending_request_count == 0:
                classification = "stale_inbox_without_unity_ownership"
                cleanup_candidate = True
        elif artifact_kind == "outbox":
            if terminal_event_type:
                classification = "stale_outbox_after_terminal_event"
                cleanup_candidate = True

        if not cleanup_candidate:
            return

        candidate_paths.append(path.resolve())
        classifications[classification] = int(classifications.get(classification) or 0) + 1
        if len(candidates) < max(0, int(max_entries)):
            candidates.append(
                {
                    "request_id": request_id,
                    "artifact_kind": artifact_kind,
                    "classification": classification,
                    "path": str(path.resolve()),
                    "age_seconds": round(age_seconds, 3),
                    "request_submitted": request_submitted,
                    "request_started": request_started,
                    "terminal_event_type": terminal_event_type,
                }
            )

    for path in inbox_dir(project_root).glob("*.json"):
        consider_path(path, "inbox")
    for path in outbox_dir(project_root).glob("*.json"):
        consider_path(path, "outbox")

    return {
        "has_stale_request_artifacts": bool(candidate_paths),
        "stale_age_seconds": max(1, int(stale_age_seconds)),
        "candidate_count": len(candidate_paths),
        "classifications": classifications,
        "candidates": candidates,
        "bridge_stabilization": stabilization,
    }


def cleanup_stale_request_artifacts(
    project_root: Path,
    *,
    current_state: dict[str, Any] | None = None,
    stale_age_seconds: int = 600,
    dry_run: bool = False,
    max_entries: int = 50,
) -> dict[str, Any]:
    inspection = inspect_stale_request_artifacts(
        project_root,
        current_state=current_state,
        stale_age_seconds=stale_age_seconds,
        max_entries=max_entries,
    )
    removal_inspection = inspect_stale_request_artifacts(
        project_root,
        current_state=current_state,
        stale_age_seconds=stale_age_seconds,
        max_entries=100000,
    )
    removed: list[str] = []
    failed: list[str] = []
    removed_bytes = 0

    for candidate in list(removal_inspection.get("candidates") or []):
        path_text = str(candidate.get("path") or "")
        if not path_text:
            continue
        path = Path(path_text)
        try:
            stat_result = path.stat()
        except OSError:
            continue

        if dry_run:
            removed.append(path_text)
            removed_bytes += int(stat_result.st_size or 0)
            continue

        try:
            path.unlink()
            removed.append(path_text)
            removed_bytes += int(stat_result.st_size or 0)
        except OSError:
            failed.append(path_text)

    return {
        "action": "request_stale_cleanup",
        "project_root": str(project_root),
        "dry_run": bool(dry_run),
        "stale_age_seconds": max(1, int(stale_age_seconds)),
        "inspection": inspection,
        "removed_count": 0 if dry_run else len(removed),
        "failed_count": 0 if dry_run else len(failed),
        "removed_bytes": 0 if dry_run else removed_bytes,
        "removed_paths": [] if dry_run else removed,
        "would_remove_count": len(removed) if dry_run else 0,
        "would_remove_bytes": removed_bytes if dry_run else 0,
        "would_remove_paths": removed if dry_run else [],
        "failed_paths": failed,
    }
