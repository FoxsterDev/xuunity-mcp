#!/usr/bin/env python3
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import server_bridge_final_status as _final_status

from server_bridge_compile_gate import compiler_diagnostics_from_state, fail_if_compile_broken_for_operation
from server_bridge_constants import (
    COMPILE_RED_FAIL_FAST_OPERATIONS,
    DEFAULT_BRIDGE_TRANSPORT,
    DEFAULT_CONFIGURED_BRIDGE_TRANSPORT,
    DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
    DEFAULT_IDLE_STABLE_CYCLES,
    SUPPORTED_BRIDGE_TRANSPORTS,
    TCP_LOOPBACK_BRIDGE_TRANSPORT,
)
from server_bridge_final_status import (
    build_bridge_stabilization_summary,
    build_lifecycle_reset_tool_error,
    build_operator_verdict,
    build_safe_retry_budget,
    build_test_verdict_summary,
    build_transport_response_missing_tool_error,
    classify_result_trust_class,
    is_test_operation,
    maybe_record_settle_lifecycle_transition,
    peek_response_payload,
    read_persisted_test_result,
    resolve_post_reset_recovery_timeout_ms,
    try_take_recovered_response,
)
from server_bridge_journal import (
    bridge_identity_changed,
    bridge_identity_from_state,
    emit_operation_progress_phase,
    emit_request_not_submitted_ack,
    emit_request_submission_ack,
    parse_journal_utc_timestamp,
    read_request_journal_events,
    record_operation_progress_event,
    record_request_submission_event,
    report_operation_progress_phase,
    write_host_request_journal_event,
)
from server_bridge_paths import (
    active_scenario_run_path,
    bridge_config_path,
    bridge_root,
    bridge_state_path,
    captures_dir,
    default_editor_log_path,
    host_editor_session_state_path,
    inbox_dir,
    logs_dir,
    outbox_dir,
    request_journal_dir,
    response_path,
    scenario_results_dir,
    scenarios_dir,
    test_result_path,
)
from server_bridge_request_artifacts import (
    cancel_request_best_effort,
    cleanup_stale_request_artifacts,
    inbox_request_path,
    inspect_stale_request_artifacts,
)
from server_bridge_state import (
    annotate_bridge_state_with_liveness,
    bridge_enabled,
    derive_busy_reason,
    expected_playmode_state_for_action,
    heartbeat_age_seconds,
    inspect_bridge_state_liveness,
    parse_utc_timestamp,
    pid_is_alive,
    read_best_effort_bridge_state,
    state_is_idle,
    summarize_state_for_error,
    try_read_bridge_config,
    try_read_bridge_state,
    try_read_live_editor_state,
    wait_for_editor_idle,
    wait_for_playmode_state,
)
from server_bridge_transport import (
    BridgeTransportAdapter,
    FileIpcBridgeTransport,
    TcpLoopbackBridgeTransport,
    invoke_bridge_transport,
    resolve_bridge_transport,
)
from server_core import ToolInvocationError, read_json, write_json

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
    original_reader = _final_status.read_request_journal_events
    _final_status.read_request_journal_events = read_request_journal_events
    try:
        return _final_status.build_request_final_status(
            project_root,
            request_id,
            operation,
            current_state=current_state,
            read_current_state=read_current_state,
            poll_timeout_ms=poll_timeout_ms,
            poll_interval_ms=poll_interval_ms,
            return_reclassified_terminal_immediately=return_reclassified_terminal_immediately,
        )
    finally:
        _final_status.read_request_journal_events = original_reader


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
