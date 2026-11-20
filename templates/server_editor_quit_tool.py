from __future__ import annotations

import argparse
import time
from typing import Any

from server_batch_orchestrator import (
    build_tool_error_payload,
    ensure_project_root,
    mcp_json_result,
    read_request_journal_events,
    request_editor_quit,
    try_read_bridge_state,
    try_read_host_editor_session_state,
    verify_project_editor_closed,
)
from server_cli_bridge_commands import run_request_editor_quit
from server_core import ToolInvocationError, parse_utc_timestamp
from server_health import FRESH_HEARTBEAT_MAX_AGE_SECONDS
from server_mcp_protocol import JsonRpcError

ACTIVE_TEST_RUN_PHASES = {"submitted", "started", "running"}
FULL_PAYLOAD_ONLY_FIELDS = ("quit_request",)


def editor_quit_busy_reasons(state: dict[str, Any] | None, *, now: float | None = None) -> list[str]:
    if not isinstance(state, dict):
        return []
    heartbeat = parse_utc_timestamp(state.get("heartbeat_utc"))
    current = time.time() if now is None else now
    if heartbeat is None or current - heartbeat > FRESH_HEARTBEAT_MAX_AGE_SECONDS:
        return []
    reasons: list[str] = []
    if bool(state.get("is_playing")) or bool(state.get("is_playing_or_will_change_playmode")):
        reasons.append("playmode_active")
    if str(state.get("active_test_run_phase") or "").strip().lower() in ACTIVE_TEST_RUN_PHASES:
        reasons.append("test_run_active")
    active_operation = str(state.get("active_operation") or "").strip()
    if active_operation:
        reasons.append(f"operation_active:{active_operation}")
    return reasons


def _int_argument(arguments: dict[str, Any], name: str, default: int, minimum: int) -> int:
    value = arguments.get(name, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise JsonRpcError(-32602, f"{name} must be an integer of at least {minimum}.")
    return value


def _bool_argument(arguments: dict[str, Any], name: str, default: bool) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise JsonRpcError(-32602, f"{name} must be a boolean.")
    return value


def call_unity_editor_quit_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    project_root_value = arguments.get("projectRoot")
    if not isinstance(project_root_value, str) or not project_root_value.strip():
        raise JsonRpcError(-32602, "projectRoot is required.")
    approve = _bool_argument(arguments, "approve", False)
    wait_for_exit = _bool_argument(arguments, "waitForExit", True)
    allow_while_busy = _bool_argument(arguments, "allowWhileBusy", False)
    include_full_payload = _bool_argument(arguments, "includeFullPayload", False)
    timeout_ms = _int_argument(arguments, "timeoutMs", 15000, 1000)
    exit_timeout_ms = _int_argument(arguments, "exitTimeoutMs", 30000, 1000)

    captured: dict[str, Any] = {}
    try:
        project_root = ensure_project_root(project_root_value)
        if not approve:
            raise ToolInvocationError(
                "editor_quit_approval_required",
                "Set approve=true to quit this project's editor. The quit closes the editor whoever opened it and "
                "discards unsaved scene and prefab changes. Nothing was executed.",
                {"project_root": str(project_root), "request_submitted": False},
            )
        busy_reasons = editor_quit_busy_reasons(try_read_bridge_state(project_root))
        if busy_reasons and not allow_while_busy:
            raise ToolInvocationError(
                "editor_quit_refused_editor_busy",
                "The editor is in Play Mode or running work that a quit would cut short "
                f"({', '.join(busy_reasons)}). Wait for it or stop it first; pass allowWhileBusy=true only when "
                "that work is yours to abandon. Nothing was executed.",
                {
                    "project_root": str(project_root),
                    "busy_reasons": busy_reasons,
                    "request_submitted": False,
                    "recommended_next_action": "wait_for_idle_or_stop_active_work_then_retry",
                    "recommended_next_tool": "unity_status_summary",
                },
            )
        run_request_editor_quit(
            argparse.Namespace(
                project_root=str(project_root),
                timeout_ms=timeout_ms,
                wait_for_exit=wait_for_exit,
                exit_timeout_ms=exit_timeout_ms,
                force_after_ms=0,
            ),
            ensure_project_root_fn=ensure_project_root,
            request_editor_quit_fn=request_editor_quit,
            verify_project_editor_closed_fn=verify_project_editor_closed,
            force_terminate_verified_project_editor_fn=_force_terminate_not_available,
            read_request_journal_events_fn=read_request_journal_events,
            read_host_editor_session_state_fn=try_read_host_editor_session_state,
            print_json_fn=captured.update,
        )
    except ToolInvocationError as exc:
        payload = build_tool_error_payload(exc)
        if not include_full_payload:
            _drop_full_payload_fields(payload)
        return mcp_json_result(payload, is_error=True)

    captured.setdefault("action", "request_editor_quit")
    if not include_full_payload:
        _drop_full_payload_fields(captured)
        captured["full_payload_tool_arguments"] = {"includeFullPayload": True}
    return mcp_json_result(captured)


def _force_terminate_not_available(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise ToolInvocationError(
        "editor_quit_force_not_available",
        "unity_editor_quit never force-terminates an editor; use the request-editor-quit CLI escalation.",
    )


def _drop_full_payload_fields(payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    for field in FULL_PAYLOAD_ONLY_FIELDS:
        payload.pop(field, None)
    for value in payload.values():
        if isinstance(value, dict):
            _drop_full_payload_fields(value)
