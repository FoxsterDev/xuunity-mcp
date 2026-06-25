#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from server_bridge_constants import DEFAULT_BRIDGE_TRANSPORT, TCP_LOOPBACK_BRIDGE_TRANSPORT
from server_bridge_journal import (
    bridge_identity_changed,
    bridge_identity_from_state,
    parse_journal_utc_timestamp,
    read_request_journal_events,
    write_host_request_journal_event,
)
from server_bridge_paths import default_editor_log_path, response_path, test_result_path
from server_bridge_state import read_best_effort_bridge_state, try_read_bridge_state
from server_core import ToolInvocationError, read_json
from server_operation_evidence import attach_operation_evidence_to_final_status

def build_bridge_stabilization_summary(
    state: dict[str, Any] | None,
    *,
    editor_running: bool | None = None,
    mcp_reachable: bool | None = None,
) -> dict[str, Any]:
    effective = state or {}
    health_status = str(effective.get("health_status") or "unknown")
    transport = str(effective.get("transport") or effective.get("transport_requested") or "")
    transport_listener_state = str(effective.get("transport_listener_state") or "")
    if transport == DEFAULT_BRIDGE_TRANSPORT and not transport_listener_state:
        transport_listener_state = "inactive"
    listener_required = transport == TCP_LOOPBACK_BRIDGE_TRANSPORT
    transport_ready_for_requests = bool(transport) and (
        not listener_required or transport_listener_state == "listening"
    )
    request_flow_state = "usable" if transport_ready_for_requests else "not_ready"
    pending_request_count = int(effective.get("pending_request_count") or 0)
    editor_running_effective = bool(editor_running if editor_running is not None else effective.get("editor_running", True))
    mcp_reachable_effective = bool(mcp_reachable if mcp_reachable is not None else effective.get("mcp_reachable", True))

    blocking_reasons: list[str] = []
    if not editor_running_effective:
        blocking_reasons.append("editor_not_running")
    if not mcp_reachable_effective:
        blocking_reasons.append("mcp_not_reachable")
    if health_status != "healthy":
        blocking_reasons.append("health_not_healthy")
    if bool(effective.get("domain_reload_in_progress")):
        blocking_reasons.append("domain_reload_in_progress")
    if bool(effective.get("asset_import_in_progress")):
        blocking_reasons.append("asset_import_in_progress")
    if bool(effective.get("package_operation_in_progress")):
        blocking_reasons.append("package_operation_in_progress")
    if bool(effective.get("compile_settle_pending")):
        blocking_reasons.append("compile_settle_pending")
    if bool(effective.get("script_compilation_failed")) or int(effective.get("compiler_error_count") or 0) > 0:
        blocking_reasons.append("compile_broken")
    if bool(effective.get("refresh_settle_pending")):
        blocking_reasons.append("refresh_settle_pending")
    if bool(effective.get("playmode_transition_pending")):
        blocking_reasons.append("playmode_transition_pending")
    if pending_request_count > 0:
        blocking_reasons.append("pending_request_in_flight")
    if listener_required and transport_listener_state not in {"", "listening"}:
        blocking_reasons.append("transport_listener_not_ready")

    stabilized = len(blocking_reasons) == 0
    return {
        "bridge_generation": int(effective.get("bridge_generation") or 0),
        "bridge_session_id": str(effective.get("bridge_session_id") or ""),
        "transport": transport,
        "health_status": health_status,
        "transport_listener_state": transport_listener_state,
        "listener_required": listener_required,
        "request_flow_state": request_flow_state,
        "transport_ready_for_requests": transport_ready_for_requests,
        "pending_request_count": pending_request_count,
        "stabilized": stabilized,
        "safe_to_retry": stabilized,
        "blocking_reasons": blocking_reasons,
    }


def classify_result_trust_class(
    *,
    operation_outcome: str,
    request_started: bool,
    request_completed: bool,
    request_observed_in_unity_journal: bool,
) -> str:
    if operation_outcome == "completed_ok":
        return "unity_completed_confirmed"
    if operation_outcome == "completed_failed":
        return "unity_failed_confirmed"
    if operation_outcome == "settled_after_lifecycle_reset":
        return "unity_completed_after_lifecycle_reset"
    if operation_outcome in {
        "retryable_after_lifecycle_reset",
        "abandoned_after_lifecycle_reset",
        "submitted_lost_after_lifecycle_churn",
        "cancellation_requested_in_flight",
    }:
        return "wrapper_failed_unity_unproven"
    if operation_outcome in {
        "cancelled_before_unity_start",
        "submitted_no_unity_journal_confirmation",
    }:
        return "request_not_observed"
    if request_completed:
        return "unity_failed_confirmed"
    if request_started or request_observed_in_unity_journal:
        return "wrapper_failed_unity_unproven"
    return "request_not_observed"


def build_safe_retry_budget(
    *,
    operation_outcome: str,
    recommended_next_action: str,
    retryable: bool,
) -> dict[str, Any]:
    retry_budget_total = 1 if (
        retryable
        or operation_outcome in {
            "retryable_after_lifecycle_reset",
            "abandoned_after_lifecycle_reset",
            "submitted_lost_after_lifecycle_churn",
            "submitted_no_unity_journal_confirmation",
            "cancelled_before_unity_start",
            "cancellation_requested_in_flight",
        }
    ) else 0
    retry_budget_remaining = 1 if (
        retry_budget_total > 0
        and recommended_next_action in {
            "retry_request",
            "wait_for_bridge_stabilization",
            "verify_effect_or_retry",
        }
    ) else 0
    return {
        "safe_retry_budget_total": retry_budget_total,
        "safe_retry_budget_remaining": retry_budget_remaining,
        "safe_retry_budget_exhausted": retry_budget_total > 0 and retry_budget_remaining == 0,
        "safe_retry_budget_blocked": retry_budget_total > 0 and recommended_next_action == "wait_for_bridge_stabilization",
    }


def build_operator_verdict(
    *,
    request_completed: bool,
    reclassified: bool,
    operation_outcome: str,
    result_trust_class: str,
    recommended_next_action: str,
) -> dict[str, Any]:
    if (
        request_completed
        and reclassified
        and result_trust_class == "unity_completed_confirmed"
        and recommended_next_action == "none"
    ):
        return {
            "status": "confirmed_success_after_lifecycle_churn",
            "message": "Unity completed the operation; lifecycle reclassification is informational.",
            "should_retry": False,
            "next_action": "continue",
        }

    if result_trust_class == "unity_completed_confirmed" and recommended_next_action == "none":
        return {
            "status": "confirmed_success",
            "message": "Unity completed the operation.",
            "should_retry": False,
            "next_action": "continue",
        }

    if result_trust_class == "wrapper_failed_unity_unproven":
        return {
            "status": "unity_completion_unproven",
            "message": "Unity completion was not proven; inspect final status and recovery evidence before retrying.",
            "should_retry": recommended_next_action in {"retry_request", "verify_effect_or_retry"},
            "next_action": recommended_next_action or "inspect_request_journal",
        }

    return {
        "status": operation_outcome or "unknown",
        "message": "Use recommended_next_action for follow-up.",
        "should_retry": recommended_next_action in {"retry_request", "verify_effect_or_retry"},
        "next_action": recommended_next_action or "inspect_request_journal",
    }


def build_request_final_status(
    project_root: Path,
    request_id: str,
    operation: str = "",
    *,
    current_state: dict[str, Any] | None = None,
    read_current_state: Callable[[Path], dict[str, Any] | None] | None = None,
    poll_timeout_ms: int = 0,
    poll_interval_ms: int = 200,
    return_reclassified_terminal_immediately: bool = True,
) -> dict[str, Any]:
    deadline = time.time() + max(0.0, poll_timeout_ms / 1000.0)

    while True:
        events = read_request_journal_events(project_root, request_id)
        if read_current_state is not None:
            active_state = read_current_state(project_root) or current_state or {}
        else:
            active_state = read_best_effort_bridge_state(project_root) or try_read_bridge_state(project_root) or current_state or {}
        stabilization = build_bridge_stabilization_summary(active_state)

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
        reclassified_events = [
            event
            for event in events
            if str(event.get("event_type") or "") in {"request_reclassified", "request_abandoned"}
        ]
        reclassified_event = reclassified_events[-1] if reclassified_events else None
        last_event = events[-1] if events else None

        request_submitted = submitted_event is not None
        completion_status = str((completed_event or {}).get("operation_status") or "")
        request_started = started_event is not None
        request_completed = completed_event is not None
        cancellation_event_type = str((cancellation_event or {}).get("event_type") or "")
        cancellation_status = str(
            (cancellation_event or {}).get("cancellation_status")
            or (cancellation_event or {}).get("reclassified_status")
            or ""
        )
        cancellation_reason = str((cancellation_event or {}).get("reason") or "")
        cancellation_requested = cancellation_event_type == "request_cancel_requested"
        request_cancelled = cancellation_event_type == "request_cancelled"
        reclassified = reclassified_event is not None
        retryable = bool((reclassified_event or {}).get("retryable")) if reclassified else False
        request_observed_in_unity_journal = request_started or request_completed

        submitted_generation = int((submitted_event or {}).get("bridge_generation") or 0)
        submitted_session_id = str((submitted_event or {}).get("bridge_session_id") or "")
        bridge_changed_since_submission = request_submitted and bridge_identity_changed(
            submitted_generation,
            submitted_session_id,
            active_state,
        )
        recovery_gap_detected = (
            request_submitted
            and not request_observed_in_unity_journal
            and bridge_changed_since_submission
            and stabilization["stabilized"]
        )

        reclassified_event_type = str((reclassified_event or {}).get("event_type") or "")
        reclassified_status = str((reclassified_event or {}).get("reclassified_status") or "")
        reclassified_reason = str((reclassified_event or {}).get("reason") or "")

        if request_completed and completion_status == "ok":
            operation_outcome = "completed_ok"
        elif request_completed:
            operation_outcome = "completed_failed"
        elif reclassified_event_type == "request_abandoned" and reclassified_status:
            operation_outcome = reclassified_status
        elif reclassified_event_type == "request_reclassified" and reclassified_status:
            operation_outcome = reclassified_status
        elif request_cancelled and cancellation_status:
            operation_outcome = cancellation_status
        elif cancellation_requested and cancellation_status:
            operation_outcome = cancellation_status
        elif recovery_gap_detected:
            operation_outcome = "submitted_lost_after_lifecycle_churn"
        elif request_submitted and not request_observed_in_unity_journal:
            operation_outcome = "submitted_no_unity_journal_confirmation"
        else:
            operation_outcome = "unknown"

        if operation_outcome == "completed_ok":
            recommended_next_action = "none"
        elif operation_outcome == "completed_failed":
            recommended_next_action = "inspect_request_journal"
        elif operation_outcome in {"retryable_after_lifecycle_reset", "abandoned_after_lifecycle_reset"}:
            recommended_next_action = (
                "retry_request" if stabilization["safe_to_retry"] else "wait_for_bridge_stabilization"
            )
        elif operation_outcome == "cancelled_before_unity_start":
            recommended_next_action = (
                "retry_request" if stabilization["safe_to_retry"] else "wait_for_bridge_stabilization"
            )
        elif operation_outcome == "cancellation_requested_in_flight":
            recommended_next_action = (
                "verify_effect_or_retry" if stabilization["safe_to_retry"] else "wait_for_bridge_stabilization"
            )
        elif operation_outcome == "settled_after_lifecycle_reset":
            recommended_next_action = "verify_effect_or_retry"
        elif operation_outcome == "submitted_lost_after_lifecycle_churn":
            recommended_next_action = "verify_effect_or_retry"
        elif operation_outcome == "submitted_no_unity_journal_confirmation" and stabilization["safe_to_retry"]:
            recommended_next_action = "retry_request"
        elif reclassified and retryable and stabilization["safe_to_retry"]:
            recommended_next_action = "retry_request"
        elif reclassified and not stabilization["safe_to_retry"]:
            recommended_next_action = "wait_for_bridge_stabilization"
        elif not request_started and stabilization["safe_to_retry"]:
            recommended_next_action = "retry_request"
        elif not stabilization["safe_to_retry"]:
            recommended_next_action = "wait_for_bridge_stabilization"
        else:
            recommended_next_action = "inspect_request_journal"

        result_trust_class = classify_result_trust_class(
            operation_outcome=operation_outcome,
            request_started=request_started,
            request_completed=request_completed,
            request_observed_in_unity_journal=request_observed_in_unity_journal,
        )
        retry_budget = build_safe_retry_budget(
            operation_outcome=operation_outcome,
            recommended_next_action=recommended_next_action,
            retryable=retryable,
        )
        operator_verdict = build_operator_verdict(
            request_completed=request_completed,
            reclassified=reclassified,
            operation_outcome=operation_outcome,
            result_trust_class=result_trust_class,
            recommended_next_action=recommended_next_action,
        )

        summary = {
            "request_id": request_id,
            "operation": str((started_event or completed_event or reclassified_event or submitted_event or {}).get("operation") or operation or ""),
            "request_submitted": request_submitted,
            "request_started": request_started,
            "request_completed": request_completed,
            "request_cancelled": request_cancelled,
            "cancellation_requested": cancellation_requested,
            "cancellation_event_type": cancellation_event_type,
            "cancellation_status": cancellation_status,
            "cancellation_reason": cancellation_reason,
            "completion_status": completion_status,
            "operation_outcome": operation_outcome,
            "reclassified": reclassified,
            "reclassified_event_type": reclassified_event_type,
            "reclassified_status": reclassified_status,
            "reclassified_reason": reclassified_reason,
            "retryable": retryable,
            "recommended_next_action": recommended_next_action,
            "result_trust_class": result_trust_class,
            "recommended_recovery_command": (
                f"request-final-status --project-root {project_root} --request-id {request_id}"
                if request_id
                else ""
            ),
            "request_submitted_at_utc": str((submitted_event or {}).get("event_at_utc") or ""),
            "request_started_at_utc": str((started_event or {}).get("started_at_utc") or (started_event or {}).get("event_at_utc") or ""),
            "request_completed_at_utc": str((completed_event or {}).get("completed_at_utc") or (completed_event or {}).get("event_at_utc") or ""),
            "last_event_type": str((last_event or {}).get("event_type") or ""),
            "last_event_at_utc": str((last_event or {}).get("event_at_utc") or ""),
            "last_bridge_generation_seen": int((last_event or {}).get("bridge_generation") or active_state.get("bridge_generation") or 0),
            "last_bridge_session_id_seen": str((last_event or {}).get("bridge_session_id") or active_state.get("bridge_session_id") or ""),
            "request_observed_in_unity_journal": request_observed_in_unity_journal,
            "bridge_changed_since_submission": bridge_changed_since_submission,
            "recovery_gap_detected": recovery_gap_detected,
            "journal_event_count": len(events),
            "journal_event_paths": [str(event.get("_path") or "") for event in events],
            "bridge_stabilization": stabilization,
            "operator_verdict": operator_verdict,
            **retry_budget,
        }

        reclassified_terminal = (
            return_reclassified_terminal_immediately
            and reclassified
            and bool(reclassified_status)
            and recommended_next_action != "wait_for_bridge_stabilization"
        )

        if request_completed or recovery_gap_detected or reclassified_terminal or time.time() >= deadline:
            response_payload = peek_response_payload(project_root, request_id)
            effective_operation = str(summary.get("operation") or operation or "")
            if is_test_operation(effective_operation):
                persisted_test_result = read_persisted_test_result(project_root, request_id)
                verdict_summary = build_test_verdict_summary(
                    project_root=project_root,
                    request_id=request_id,
                    operation=effective_operation,
                    response_payload=response_payload,
                    persisted_test_result=persisted_test_result,
                    request_submitted=request_submitted,
                    request_started=request_started,
                    request_completed=request_completed,
                    completion_status=completion_status,
                    operation_outcome=operation_outcome,
                    active_state=active_state,
                    bridge_changed_since_submission=bridge_changed_since_submission,
                )
                summary["operation_recommended_next_action"] = summary.get("recommended_next_action")
                summary["operation_result_trust_class"] = summary.get("result_trust_class")
                if not verdict_summary["result_payload_available"] and not request_completed:
                    verdict_summary["recommended_next_action"] = str(summary.get("recommended_next_action") or "")
                summary.update(verdict_summary)
                summary["operator_verdict"] = build_operator_verdict(
                    request_completed=request_completed,
                    reclassified=reclassified,
                    operation_outcome=str(summary.get("operation_outcome") or ""),
                    result_trust_class=str(summary.get("result_trust_class") or ""),
                    recommended_next_action=str(summary.get("recommended_next_action") or ""),
                )
                summary["playmode_verdict_summary"] = dict(verdict_summary)
            return attach_operation_evidence_to_final_status(
                summary,
                project_root=project_root,
                payload=response_payload,
                editor_log_path=default_editor_log_path(project_root),
            )

        time.sleep(max(0.05, poll_interval_ms / 1000.0))


def try_take_recovered_response(project_root: Path, request_id: str) -> dict[str, Any] | None:
    path = response_path(project_root, request_id)
    if not path.is_file():
        return None

    try:
        return read_json(path)
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def peek_response_payload(project_root: Path, request_id: str) -> dict[str, Any] | None:
    path = response_path(project_root, request_id)
    if not path.is_file():
        return None

    try:
        response = read_json(path)
    except Exception:
        return None

    if not isinstance(response, dict):
        return None

    payload_json = response.get("payload_json")
    if not isinstance(payload_json, str) or not payload_json:
        return None

    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def read_persisted_test_result(project_root: Path, request_id: str) -> dict[str, Any] | None:
    if not request_id:
        return None

    path = test_result_path(project_root, request_id)
    if not path.is_file():
        return None

    try:
        payload = read_json(path)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    payload["_path"] = str(path)
    return payload


def is_test_operation(operation: str) -> bool:
    return operation in {"unity.tests.run_playmode", "unity.tests.run_editmode"}


def _first_failures(value: Any, limit: int = 3) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    failures: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        failures.append(
            {
                "name": str(item.get("name") or ""),
                "message": str(item.get("message") or ""),
            }
        )
        if len(failures) >= limit:
            break
    return failures


def _counts_from_test_payload(payload: dict[str, Any] | None) -> tuple[int, int, int, int]:
    if not isinstance(payload, dict):
        return 0, 0, 0, 0
    return (
        max(0, int(payload.get("total") or 0)),
        max(0, int(payload.get("passed") or 0)),
        max(0, int(payload.get("failed") or 0)),
        max(0, int(payload.get("skipped") or 0)),
    )


def _runtime_deadline_expired(test_result: dict[str, Any] | None) -> bool:
    if not isinstance(test_result, dict):
        return False

    runtime_timeout_ms = max(1000, int(test_result.get("runtime_timeout_ms") or test_result.get("request_timeout_ms") or 0))
    baseline_utc = str(test_result.get("last_progress_at_utc") or test_result.get("started_at_utc") or "")
    baseline_unix = parse_journal_utc_timestamp(baseline_utc)
    if baseline_unix <= 0:
        return False
    return time.time() >= baseline_unix + (runtime_timeout_ms / 1000.0)


def _derive_timeout_classification(test_result: dict[str, Any] | None) -> str:
    if not isinstance(test_result, dict):
        return ""

    explicit = str(test_result.get("timeout_classification") or "")
    if explicit:
        return explicit

    run_phase = str(test_result.get("run_phase") or "")
    last_progress_at_utc = str(test_result.get("last_progress_at_utc") or "")
    last_started_test = str(test_result.get("last_started_test") or "")
    last_finished_test = str(test_result.get("last_finished_test") or "")
    if run_phase in {"started", "running", "timed_out"} or last_progress_at_utc or last_started_test or last_finished_test:
        return "runtime_timeout_after_test_start"
    return "timeout_before_test_start"


def build_test_verdict_summary(
    *,
    project_root: Path,
    request_id: str,
    operation: str,
    response_payload: dict[str, Any] | None,
    persisted_test_result: dict[str, Any] | None,
    request_submitted: bool,
    request_started: bool,
    request_completed: bool,
    completion_status: str,
    operation_outcome: str,
    active_state: dict[str, Any] | None,
    bridge_changed_since_submission: bool,
) -> dict[str, Any]:
    source_payload: dict[str, Any] | None = None
    source = "none"
    reason = "no_result_payload_or_artifact"

    if isinstance(response_payload, dict):
        source_payload = response_payload
        source = "response_payload"
        reason = "response_payload_available"
    elif isinstance(persisted_test_result, dict):
        source_payload = persisted_test_result
        source = "persisted_test_result"
        reason = "persisted_test_result_available"
    elif request_completed:
        source = "journal_only"
        reason = "response_missing_after_completed_request"
    elif request_started:
        source = "journal_only"
        reason = "request_started_without_result_payload"
    elif request_submitted:
        source = "journal_only"
        reason = "request_not_observed_in_unity_journal"

    total, passed, failed, skipped = _counts_from_test_payload(source_payload)
    run_phase = str((source_payload or {}).get("run_phase") or "")
    source_completed = bool(str((source_payload or {}).get("completed_at_utc") or ""))
    explicit_timeout_classification = str((source_payload or {}).get("timeout_classification") or "")
    timeout_classification = (
        explicit_timeout_classification
        if explicit_timeout_classification or not source_completed
        else ""
    )
    if not source_completed and not timeout_classification:
        timeout_classification = _derive_timeout_classification(source_payload)
    runtime_timeout_observed = (
        not source_completed
        and (
            run_phase in {"timed_out", "settled_after_timeout"}
            or (
                timeout_classification == "runtime_timeout_after_test_start"
                and _runtime_deadline_expired(source_payload)
            )
        )
    )

    if source_payload is not None and (run_phase == "timed_out" or runtime_timeout_observed):
        test_verdict = "runtime_timeout"
    elif source_payload is not None and (request_completed or source_completed):
        if total <= 0:
            test_verdict = "no_tests"
        elif failed > 0:
            test_verdict = "failed"
        else:
            test_verdict = "passed"
    elif source_payload is not None and _runtime_deadline_expired(source_payload):
        timeout_classification = timeout_classification or _derive_timeout_classification(source_payload)
        test_verdict = "runtime_timeout" if timeout_classification == "runtime_timeout_after_test_start" else "unity_unproven"
    elif source_payload is not None and run_phase == "abandoned":
        test_verdict = "unity_unproven"
    elif source_payload is not None:
        test_verdict = "in_progress"
    elif request_completed and completion_status == "ok":
        test_verdict = "unity_unproven"
    elif not request_started and request_submitted:
        test_verdict = "infrastructure_error"
    elif operation_outcome in {"submitted_no_unity_journal_confirmation", "submitted_lost_after_lifecycle_churn"}:
        test_verdict = "infrastructure_error"
    else:
        test_verdict = "unity_unproven"

    playmode_state = str((active_state or {}).get("playmode_state") or "")
    cleanup_recommended = test_verdict in {"runtime_timeout", "unity_unproven", "in_progress"} and playmode_state in {
        "playing",
        "paused",
        "will_enter_playmode",
        "will_exit_playmode",
        "transitioning",
    }

    if test_verdict == "runtime_timeout":
        recommended_next_action = "inspect_test_timeout_or_raise_budget"
        trust_class = "unity_failed_confirmed"
    elif test_verdict == "failed":
        recommended_next_action = "inspect_test_failures"
        trust_class = "unity_failed_confirmed"
    elif test_verdict in {"passed", "no_tests"}:
        recommended_next_action = "none"
        trust_class = "unity_completed_confirmed"
    elif test_verdict == "in_progress":
        recommended_next_action = "wait_for_final_status"
        trust_class = "unity_unproven"
    elif test_verdict == "infrastructure_error":
        recommended_next_action = "retry_after_readiness_recovery"
        trust_class = "request_not_observed"
    else:
        recommended_next_action = "inspect_artifacts_before_retry"
        trust_class = "wrapper_failed_unity_unproven"

    runtime_timeout_ms = int((source_payload or {}).get("runtime_timeout_ms") or (source_payload or {}).get("request_timeout_ms") or 0)
    elapsed_runtime_seconds = None
    baseline_unix = parse_journal_utc_timestamp(str((source_payload or {}).get("last_progress_at_utc") or (source_payload or {}).get("started_at_utc") or ""))
    if baseline_unix > 0:
        elapsed_runtime_seconds = round(max(0.0, time.time() - baseline_unix), 3)

    return {
        "result_payload_available": source_payload is not None,
        "result_payload_source": source,
        "result_payload_reason": reason,
        "test_verdict": test_verdict,
        "run_phase": run_phase,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "first_failures": _first_failures((source_payload or {}).get("failures")),
        "last_started_test": str((source_payload or {}).get("last_started_test") or ""),
        "last_finished_test": str((source_payload or {}).get("last_finished_test") or ""),
        "last_progress_at_utc": str((source_payload or {}).get("last_progress_at_utc") or ""),
        "runtime_timeout_observed": runtime_timeout_observed or test_verdict == "runtime_timeout",
        "timeout_classification": timeout_classification,
        "runtime_timeout_ms": max(0, runtime_timeout_ms),
        "elapsed_runtime_seconds": elapsed_runtime_seconds,
        "lifecycle_churn_observed": bool((source_payload or {}).get("lifecycle_churn_observed")) or bridge_changed_since_submission,
        "editor_cleanup_recommended": cleanup_recommended,
        "cleanup_command": (
            f"request-playmode-set --project-root {project_root} --action exit --timeout-ms 30000"
            if cleanup_recommended
            else ""
        ),
        "playmode_state": playmode_state,
        "recommended_next_action": recommended_next_action,
        "result_trust_class": trust_class,
    }


def try_recover_completed_response_after_reset(
    project_root: Path,
    *,
    request_id: str,
    operation: str,
    current_state: dict[str, Any] | None,
    poll_timeout_ms: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    final_status = build_request_final_status(
        project_root,
        request_id,
        operation,
        current_state=current_state,
        poll_timeout_ms=poll_timeout_ms,
        return_reclassified_terminal_immediately=False,
    )

    if bool(final_status.get("request_completed")):
        recovered_response = try_take_recovered_response(project_root, request_id)
        if recovered_response is not None:
            return recovered_response, final_status

    return None, final_status


def resolve_post_reset_recovery_timeout_ms(
    request_deadline_unix: float,
    post_reset_recovery_cap_ms: int,
) -> int:
    remaining_ms = max(0, int((request_deadline_unix - time.time()) * 1000))
    if remaining_ms <= 0:
        return 0

    cap_ms = max(0, int(post_reset_recovery_cap_ms or 0))
    if cap_ms > 0:
        return min(remaining_ms, cap_ms)
    return remaining_ms


def build_lifecycle_reset_tool_error(
    project_root: Path,
    *,
    request_id: str,
    operation: str,
    transport: str,
    initial_bridge_generation: int,
    initial_bridge_session_id: str,
    current_state: dict[str, Any] | None,
    journal_event_path: Path | None = None,
    retryable_hint: bool | None = None,
    request_processed_hint: bool | None = None,
    transport_host: str = "",
    transport_port: int = 0,
    poll_timeout_ms: int = 1500,
) -> ToolInvocationError:
    _, final_status = try_recover_completed_response_after_reset(
        project_root,
        request_id=request_id,
        operation=operation,
        current_state=current_state,
        poll_timeout_ms=poll_timeout_ms,
    )
    stabilization = final_status.get("bridge_stabilization") or {}
    current_generation = int(stabilization.get("bridge_generation") or 0)
    current_session_id = str(stabilization.get("bridge_session_id") or "")
    operation_outcome = str(final_status.get("operation_outcome") or "unknown")
    recommended_next_action = str(final_status.get("recommended_next_action") or "inspect_request_journal")
    result_trust_class = str(final_status.get("result_trust_class") or "")
    recommended_recovery_command = (
        f"request-final-status --project-root {project_root} --request-id {request_id}"
    )

    message = (
        "The response channel reset before the wrapper could return the result. "
        f"request_id: {request_id} "
        "transport_outcome: reset_before_response_commit "
        f"operation_outcome: {operation_outcome} "
        f"result_trust_class: {result_trust_class or 'unknown'} "
        f"recommended_next_action: {recommended_next_action} "
        f"next_step: {recommended_recovery_command}"
    )
    code = "request_lifecycle_reset"
    if operation_outcome == "completed_ok":
        message = (
            "The response channel reset before the wrapper could return the result. "
            "The Unity operation completed successfully, but the response payload was not observed. "
            f"request_id: {request_id} "
            "transport_outcome: reset_before_response_commit "
            "operation_outcome: completed_ok "
            "result_trust_class: unity_completed_confirmed "
            "recommended_next_action: none "
            f"next_step: {recommended_recovery_command}"
        )
        code = "response_missing_after_lifecycle_reset"
    elif operation_outcome == "completed_failed":
        message = (
            "The response channel reset before the wrapper could return the result. "
            "The Unity operation completed with a failure status, but the response payload was not observed. "
            f"request_id: {request_id} "
            "transport_outcome: reset_before_response_commit "
            "operation_outcome: completed_failed "
            "result_trust_class: unity_failed_confirmed "
            "recommended_next_action: inspect_request_journal "
            f"next_step: {recommended_recovery_command}"
        )
        code = "response_missing_after_lifecycle_reset"
    else:
        message = (
            message + ". The Unity operation may still have completed."
        )

    details: dict[str, Any] = {
        "request_id": request_id,
        "operation": operation,
        "transport": transport,
        "transport_outcome": "reset_before_response_commit",
        "operation_outcome": operation_outcome,
        "recommended_next_action": recommended_next_action,
        "result_trust_class": result_trust_class,
        "recommended_recovery_command": recommended_recovery_command,
        "initial_bridge_generation": initial_bridge_generation,
        "initial_bridge_session_id": initial_bridge_session_id,
        "current_bridge_generation": current_generation,
        "current_bridge_session_id": current_session_id,
        "retryable": bool(retryable_hint if retryable_hint is not None else final_status.get("retryable")),
        "request_processed": bool(request_processed_hint if request_processed_hint is not None else final_status.get("request_completed")),
        "request_final_status": final_status,
        "bridge_stabilization": stabilization,
        "safe_retry_budget_total": int(final_status.get("safe_retry_budget_total") or 0),
        "safe_retry_budget_remaining": int(final_status.get("safe_retry_budget_remaining") or 0),
        "safe_retry_budget_exhausted": bool(final_status.get("safe_retry_budget_exhausted")),
        "safe_retry_budget_blocked": bool(final_status.get("safe_retry_budget_blocked")),
    }
    if journal_event_path is not None:
        details["journal_event_path"] = str(journal_event_path)
    if transport_host:
        details["host"] = transport_host
    if transport_port > 0:
        details["port"] = transport_port
    return ToolInvocationError(code, message, details)


def build_transport_response_missing_tool_error(
    project_root: Path,
    *,
    request_id: str,
    operation: str,
    transport: str,
    current_state: dict[str, Any] | None,
    transport_host: str = "",
    transport_port: int = 0,
    poll_timeout_ms: int = 1000,
) -> ToolInvocationError:
    final_status = build_request_final_status(
        project_root,
        request_id,
        operation,
        current_state=current_state,
        poll_timeout_ms=poll_timeout_ms,
    )
    stabilization = final_status.get("bridge_stabilization") or {}
    operation_outcome = str(final_status.get("operation_outcome") or "unknown")
    result_trust_class = str(final_status.get("result_trust_class") or "")
    request_processed = bool(final_status.get("request_started") or final_status.get("request_completed"))
    recommended_next_action = str(final_status.get("recommended_next_action") or "retry_request")
    recommended_recovery_command = (
        f"request-final-status --project-root {project_root} --request-id {request_id}"
    )

    if request_processed:
        message = (
            "The TCP loopback transport closed before the wrapper observed a response payload. "
            f"request_id: {request_id} "
            "transport_outcome: response_missing_without_reset_signal "
            f"operation_outcome: {operation_outcome} "
            f"result_trust_class: {result_trust_class or 'unknown'} "
            f"recommended_next_action: {recommended_next_action} "
            f"next_step: {recommended_recovery_command}"
        )
    else:
        message = (
            "The TCP loopback transport closed before the request was observed in the Unity request journal. "
            f"request_id: {request_id} "
            "transport_outcome: response_missing_without_reset_signal "
            "operation_outcome: unknown "
            "recommended_next_action: retry_request "
            f"next_step: {recommended_recovery_command}"
        )

    details: dict[str, Any] = {
        "request_id": request_id,
        "operation": operation,
        "transport": transport,
        "transport_outcome": "response_missing_without_reset_signal",
        "operation_outcome": operation_outcome,
        "recommended_next_action": recommended_next_action,
        "result_trust_class": result_trust_class,
        "recommended_recovery_command": recommended_recovery_command,
        "retryable": bool(final_status.get("retryable")) if request_processed else True,
        "request_processed": request_processed,
        "request_final_status": final_status,
        "bridge_stabilization": stabilization,
        "safe_retry_budget_total": int(final_status.get("safe_retry_budget_total") or 0),
        "safe_retry_budget_remaining": int(final_status.get("safe_retry_budget_remaining") or 0),
        "safe_retry_budget_exhausted": bool(final_status.get("safe_retry_budget_exhausted")),
        "safe_retry_budget_blocked": bool(final_status.get("safe_retry_budget_blocked")),
    }
    if transport_host:
        details["host"] = transport_host
    if transport_port > 0:
        details["port"] = transport_port
    return ToolInvocationError("transport_response_missing", message, details)


def maybe_record_settle_lifecycle_transition(
    project_root: Path,
    operation: str,
    request_id: str,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    initial_generation, initial_session_id = bridge_identity_from_state(before_state)
    current_generation, current_session_id = bridge_identity_from_state(after_state)
    if not bridge_identity_changed(initial_generation, initial_session_id, after_state):
        return None

    journal_path = write_host_request_journal_event(
        project_root,
        "request_reclassified",
        {
            "request_id": request_id,
            "operation": operation,
            "reason": "bridge_generation_changed_during_post_request_settle",
            "retryable": False,
            "reclassified_status": "settled_after_lifecycle_reset",
            "previous_bridge_generation": initial_generation,
            "previous_bridge_session_id": initial_session_id,
            "bridge_generation": current_generation,
            "bridge_session_id": current_session_id,
        },
    )
    return {
        "request_id": request_id,
        "operation": operation,
        "previous_bridge_generation": initial_generation,
        "previous_bridge_session_id": initial_session_id,
        "current_bridge_generation": current_generation,
        "current_bridge_session_id": current_session_id,
        "journal_event_path": str(journal_path),
        "reclassified_status": "settled_after_lifecycle_reset",
    }
