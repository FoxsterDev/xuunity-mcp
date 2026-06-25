#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import time
import uuid
from pathlib import Path
from typing import Any

from server_bridge_constants import (
    DEFAULT_BRIDGE_TRANSPORT,
    DEFAULT_CONFIGURED_BRIDGE_TRANSPORT,
    SUPPORTED_BRIDGE_TRANSPORTS,
    TCP_LOOPBACK_BRIDGE_TRANSPORT,
)
from server_bridge_final_status import (
    build_lifecycle_reset_tool_error,
    build_transport_response_missing_tool_error,
    resolve_post_reset_recovery_timeout_ms,
    try_recover_completed_response_after_reset,
)
from server_bridge_journal import (
    bridge_identity_changed,
    bridge_identity_from_state,
    emit_request_not_submitted_ack,
    emit_request_submission_ack,
    record_request_submission_event,
    write_host_request_journal_event,
)
from server_bridge_paths import bridge_state_path, inbox_dir, outbox_dir, request_journal_dir
from server_bridge_state import (
    bridge_enabled,
    inspect_bridge_state_liveness,
    read_best_effort_bridge_state,
    summarize_state_for_error,
    try_read_bridge_config,
    try_read_bridge_state,
)
from server_core import ToolInvocationError, read_json, write_json

class BridgeTransportAdapter:
    name = "unknown"

    def metadata(self, project_root: Path) -> dict[str, Any]:
        return {
            "name": self.name,
        }

    def invoke(
        self,
        project_root: Path,
        operation: str,
        args: dict[str, Any],
        timeout_ms: int,
        post_reset_recovery_cap_ms: int = 0,
    ) -> tuple[dict[str, Any], str, float]:
        raise NotImplementedError


class FileIpcBridgeTransport(BridgeTransportAdapter):
    name = DEFAULT_BRIDGE_TRANSPORT

    def metadata(self, project_root: Path) -> dict[str, Any]:
        return {
            "name": self.name,
            "state_path": str(bridge_state_path(project_root)),
            "request_directory": str(inbox_dir(project_root)),
            "response_directory": str(outbox_dir(project_root)),
            "journal_directory": str(request_journal_dir(project_root)),
        }

    def invoke(
        self,
        project_root: Path,
        operation: str,
        args: dict[str, Any],
        timeout_ms: int,
        post_reset_recovery_cap_ms: int = 0,
    ) -> tuple[dict[str, Any], str, float]:
        state_path = bridge_state_path(project_root)
        if not state_path.is_file():
            emit_request_not_submitted_ack(
                project_root=project_root,
                operation=operation,
                transport_name=self.name,
                reason="bridge_state_missing",
            )
            raise ToolInvocationError(
                "editor_not_running",
                f"Bridge state file not found: {state_path}",
                {
                    "request_submitted": False,
                    "request_ownership_acquired": False,
                    "transport_outcome": "request_not_submitted",
                    "operation_outcome": "request_not_dispatched",
                    "recommended_next_action": "start_or_recover_editor",
                    "transport": self.name,
                },
            )

        in_dir = inbox_dir(project_root)
        out_dir = outbox_dir(project_root)
        in_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        request_id = str(uuid.uuid4())
        request_path = in_dir / f"{request_id}.json"
        response_path = out_dir / f"{request_id}.json"
        request_started_at = time.time()
        initial_state = read_best_effort_bridge_state(project_root)
        initial_generation, initial_session_id = bridge_identity_from_state(initial_state)
        observed_reset_state: dict[str, Any] | None = None

        request = {
            "request_id": request_id,
            "operation": operation,
            "project_root": str(project_root),
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "timeout_ms": timeout_ms,
            "args_json": json.dumps(args, ensure_ascii=True, separators=(",", ":")),
        }

        write_json(request_path, request)
        emit_request_submission_ack(
            project_root=project_root,
            operation=operation,
            request_id=request_id,
            transport_name=self.name,
            state=initial_state,
        )
        record_request_submission_event(
            project_root=project_root,
            request_id=request_id,
            operation=operation,
            transport_name=self.name,
            state=initial_state,
        )

        deadline = time.time() + (timeout_ms / 1000.0)
        while time.time() < deadline:
            if response_path.is_file():
                try:
                    response = read_json(response_path)
                finally:
                    try:
                        response_path.unlink()
                    except OSError:
                        pass
                return response, request_id, request_started_at

            current_state = read_best_effort_bridge_state(project_root)
            if observed_reset_state is None and bridge_identity_changed(initial_generation, initial_session_id, current_state):
                observed_reset_state = current_state

            time.sleep(0.2)

        state = read_best_effort_bridge_state(project_root)
        if observed_reset_state is not None:
            state = state or observed_reset_state
            recovery_timeout_ms = resolve_post_reset_recovery_timeout_ms(deadline, post_reset_recovery_cap_ms)
            recovered_response, _ = try_recover_completed_response_after_reset(
                project_root,
                request_id=request_id,
                operation=operation,
                current_state=state,
                poll_timeout_ms=recovery_timeout_ms,
            )
            if recovered_response is not None:
                return recovered_response, request_id, request_started_at

            current_generation, current_session_id = bridge_identity_from_state(state)
            processed = str((state or {}).get("last_processed_request_id") or "") == request_id
            retryable = not processed
            journal_path = write_host_request_journal_event(
                project_root,
                "request_reclassified",
                {
                    "request_id": request_id,
                    "operation": operation,
                    "reason": "bridge_generation_changed_before_response",
                    "retryable": retryable,
                    "reclassified_status": (
                        "retryable_after_lifecycle_reset"
                        if retryable
                        else "response_missing_after_lifecycle_reset"
                    ),
                    "previous_bridge_generation": initial_generation,
                    "previous_bridge_session_id": initial_session_id,
                    "bridge_generation": current_generation,
                    "bridge_session_id": current_session_id,
                },
            )
            try:
                if request_path.exists():
                    request_path.unlink()
            except OSError:
                pass
            raise build_lifecycle_reset_tool_error(
                project_root,
                request_id=request_id,
                operation=operation,
                transport=self.name,
                initial_bridge_generation=initial_generation,
                initial_bridge_session_id=initial_session_id,
                current_state=state,
                journal_event_path=journal_path,
                retryable_hint=retryable,
                request_processed_hint=processed,
                poll_timeout_ms=recovery_timeout_ms,
            )

        raise ToolInvocationError(
            "operation_timeout",
            f"Timed out waiting for {response_path}. transport={self.name}. {summarize_state_for_error(state)}",
        )


class TcpLoopbackBridgeTransport(BridgeTransportAdapter):
    name = TCP_LOOPBACK_BRIDGE_TRANSPORT

    def metadata(self, project_root: Path) -> dict[str, Any]:
        state = read_best_effort_bridge_state(project_root) or try_read_bridge_state(project_root) or {}
        return {
            "name": self.name,
            "requested_transport": str(state.get("transport_requested") or self.name),
            "listener_state": str(state.get("transport_listener_state") or ""),
            "host": str(state.get("transport_host") or "127.0.0.1"),
            "port": int(state.get("transport_port") or 0),
            "state_path": str(bridge_state_path(project_root)),
            "journal_directory": str(request_journal_dir(project_root)),
        }

    def invoke(
        self,
        project_root: Path,
        operation: str,
        args: dict[str, Any],
        timeout_ms: int,
        post_reset_recovery_cap_ms: int = 0,
    ) -> tuple[dict[str, Any], str, float]:
        raw_state = try_read_bridge_state(project_root)
        state = read_best_effort_bridge_state(project_root)
        if state is None and raw_state is not None:
            liveness = inspect_bridge_state_liveness(raw_state)
            if not bool(liveness.get("editor_pid_alive")):
                stale_pid = int(liveness.get("editor_pid") or 0)
                stale_listener_state = str(raw_state.get("transport_listener_state") or "")
                stale_host = str(raw_state.get("transport_host") or "127.0.0.1")
                stale_port = int(raw_state.get("transport_port") or 0)
                raise ToolInvocationError(
                    "editor_not_running",
                    (
                        "Unity editor is not running for this project. "
                        f"Found stale bridge state with editor_pid={stale_pid}, "
                        f"listener_state={stale_listener_state or 'unknown'}, "
                        f"host={stale_host}, port={stale_port}. "
                        "Reopen Unity or run ensure-ready --open-editor."
                    ),
                    {
                        "transport": self.name,
                        "state_path": str(bridge_state_path(project_root)),
                        "state_liveness": liveness,
                    },
                )

        host = str((state or {}).get("transport_host") or "127.0.0.1")
        port = int((state or {}).get("transport_port") or 0)
        listener_state = str((state or {}).get("transport_listener_state") or "")
        if port <= 0:
            raise ToolInvocationError(
                "transport_not_ready",
                (
                    f"TCP loopback transport is not ready. "
                    f"listener_state={listener_state or 'unknown'} host={host} port={port}."
                ),
            )

        request_id = str(uuid.uuid4())
        request_started_at = time.time()
        initial_state = state
        initial_generation, initial_session_id = bridge_identity_from_state(initial_state)
        observed_reset_state: dict[str, Any] | None = None
        request = {
            "request_id": request_id,
            "operation": operation,
            "project_root": str(project_root),
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "timeout_ms": timeout_ms,
            "args_json": json.dumps(args, ensure_ascii=True, separators=(",", ":")),
        }
        payload = (json.dumps(request, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
        deadline = time.time() + (timeout_ms / 1000.0)
        chunks: list[bytes] = []

        try:
            connect_timeout = max(1.0, min(5.0, timeout_ms / 1000.0))
            with socket.create_connection((host, port), timeout=connect_timeout) as sock:
                sock.settimeout(0.2)
                sock.sendall(payload)
                emit_request_submission_ack(
                    project_root=project_root,
                    operation=operation,
                    request_id=request_id,
                    transport_name=self.name,
                    state=initial_state,
                )
                record_request_submission_event(
                    project_root=project_root,
                    request_id=request_id,
                    operation=operation,
                    transport_name=self.name,
                    state=initial_state,
                )
                try:
                    sock.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

                while time.time() < deadline:
                    try:
                        chunk = sock.recv(65536)
                        if chunk:
                            chunks.append(chunk)
                            continue
                        break
                    except socket.timeout:
                        current_state = read_best_effort_bridge_state(project_root)
                        if observed_reset_state is None and bridge_identity_changed(initial_generation, initial_session_id, current_state):
                            observed_reset_state = current_state
                        continue
                    except OSError as exc:
                        current_state = read_best_effort_bridge_state(project_root)
                        if observed_reset_state is None and bridge_identity_changed(initial_generation, initial_session_id, current_state):
                            observed_reset_state = current_state
                            break
                        raise ToolInvocationError(
                            "transport_io_failed",
                            (
                                f"TCP loopback transport failed for {operation}: {exc}. "
                                f"host={host} port={port}."
                            ),
                            {
                                "request_id": request_id,
                                "operation": operation,
                                "transport": self.name,
                                "host": host,
                                "port": port,
                            },
                        ) from exc
        except ToolInvocationError:
            raise
        except OSError as exc:
            emit_request_not_submitted_ack(
                project_root=project_root,
                operation=operation,
                transport_name=self.name,
                reason="transport_connect_failed",
            )
            raise ToolInvocationError(
                "transport_connect_failed",
                (
                    f"Failed to connect to TCP loopback transport for {operation}: {exc}. "
                    f"host={host} port={port} listener_state={listener_state or 'unknown'}."
                ),
                {
                    "request_id": request_id,
                    "request_submitted": False,
                    "request_ownership_acquired": False,
                    "operation": operation,
                    "transport_outcome": "request_not_submitted",
                    "operation_outcome": "request_not_dispatched",
                    "recommended_next_action": "request_status_summary_then_retry",
                    "transport": self.name,
                    "host": host,
                    "port": port,
                    "listener_state": listener_state,
                },
            ) from exc

        if chunks:
            try:
                response = json.loads(b"".join(chunks).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ToolInvocationError(
                    "transport_response_invalid",
                    f"TCP loopback transport returned invalid JSON for {operation}: {exc}.",
                    {
                        "request_id": request_id,
                        "operation": operation,
                        "transport": self.name,
                        "host": host,
                        "port": port,
                    },
                ) from exc
            if response.get("status") == "error":
                error = response.get("error") or {}
                error_code = str(error.get("code") or "")
                if error_code == "transport_restarting":
                    current_state = read_best_effort_bridge_state(project_root)
                    recovery_timeout_ms = resolve_post_reset_recovery_timeout_ms(deadline, post_reset_recovery_cap_ms)
                    recovered_response, _ = try_recover_completed_response_after_reset(
                        project_root,
                        request_id=request_id,
                        operation=operation,
                        current_state=current_state,
                        poll_timeout_ms=recovery_timeout_ms,
                    )
                    if recovered_response is not None:
                        return recovered_response, request_id, request_started_at

                    current_generation, current_session_id = bridge_identity_from_state(current_state)
                    journal_path = write_host_request_journal_event(
                        project_root,
                        "request_reclassified",
                        {
                            "request_id": request_id,
                            "operation": operation,
                            "reason": "bridge_generation_changed_before_response",
                            "retryable": True,
                            "reclassified_status": "retryable_after_lifecycle_reset",
                            "previous_bridge_generation": initial_generation,
                            "previous_bridge_session_id": initial_session_id,
                            "bridge_generation": current_generation,
                            "bridge_session_id": current_session_id,
                        },
                    )
                    raise build_lifecycle_reset_tool_error(
                        project_root,
                        request_id=request_id,
                        operation=operation,
                        transport=self.name,
                        initial_bridge_generation=initial_generation,
                        initial_bridge_session_id=initial_session_id,
                        current_state=current_state,
                        journal_event_path=journal_path,
                        retryable_hint=True,
                        transport_host=host,
                        transport_port=port,
                        poll_timeout_ms=recovery_timeout_ms,
                    )
            return response, request_id, request_started_at

        state = read_best_effort_bridge_state(project_root)
        if observed_reset_state is not None:
            state = state or observed_reset_state
            recovery_timeout_ms = resolve_post_reset_recovery_timeout_ms(deadline, post_reset_recovery_cap_ms)
            recovered_response, _ = try_recover_completed_response_after_reset(
                project_root,
                request_id=request_id,
                operation=operation,
                current_state=state,
                poll_timeout_ms=recovery_timeout_ms,
            )
            if recovered_response is not None:
                return recovered_response, request_id, request_started_at

            current_generation, current_session_id = bridge_identity_from_state(state)
            processed = str((state or {}).get("last_processed_request_id") or "") == request_id
            retryable = not processed
            journal_path = write_host_request_journal_event(
                project_root,
                "request_reclassified",
                {
                    "request_id": request_id,
                    "operation": operation,
                    "reason": "bridge_generation_changed_before_response",
                    "retryable": retryable,
                    "reclassified_status": (
                        "retryable_after_lifecycle_reset"
                        if retryable
                        else "response_missing_after_lifecycle_reset"
                    ),
                    "previous_bridge_generation": initial_generation,
                    "previous_bridge_session_id": initial_session_id,
                    "bridge_generation": current_generation,
                    "bridge_session_id": current_session_id,
                },
            )
            raise build_lifecycle_reset_tool_error(
                project_root,
                request_id=request_id,
                operation=operation,
                transport=self.name,
                initial_bridge_generation=initial_generation,
                initial_bridge_session_id=initial_session_id,
                current_state=state,
                journal_event_path=journal_path,
                retryable_hint=retryable,
                request_processed_hint=processed,
                transport_host=host,
                transport_port=port,
                poll_timeout_ms=recovery_timeout_ms,
            )

        raise build_transport_response_missing_tool_error(
            project_root,
            request_id=request_id,
            operation=operation,
            transport=self.name,
            current_state=state,
            transport_host=host,
            transport_port=port,
        )


def resolve_bridge_transport(project_root: Path) -> BridgeTransportAdapter:
    config = try_read_bridge_config(project_root) or {}
    state = read_best_effort_bridge_state(project_root) or {}
    state_transport = str(state.get("transport") or "").strip().lower()
    if state_transport:
        configured_transport = state_transport
    else:
        bridge_version = int(state.get("bridge_version") or 0)
        configured_transport = (
            DEFAULT_BRIDGE_TRANSPORT
            if bridge_version > 0
            else str(
                config.get("transport")
                or config.get("bridge_transport")
                or DEFAULT_CONFIGURED_BRIDGE_TRANSPORT
            ).strip().lower()
        )
    if not configured_transport:
        configured_transport = DEFAULT_BRIDGE_TRANSPORT

    if configured_transport == DEFAULT_BRIDGE_TRANSPORT:
        return FileIpcBridgeTransport()

    if configured_transport == TCP_LOOPBACK_BRIDGE_TRANSPORT:
        return TcpLoopbackBridgeTransport()

    supported = ", ".join(sorted(SUPPORTED_BRIDGE_TRANSPORTS))
    raise ToolInvocationError(
        "unsupported_bridge_transport",
        (
            f"Unsupported bridge transport '{configured_transport}'. "
            f"Supported transports: {supported}."
        ),
    )


def invoke_bridge_transport(
    project_root: Path,
    operation: str,
    args: dict[str, Any],
    timeout_ms: int,
    post_reset_recovery_cap_ms: int = 0,
) -> tuple[dict[str, Any], str, float, dict[str, Any]]:
    if not bridge_enabled(project_root):
        emit_request_not_submitted_ack(
            project_root=project_root,
            operation=operation,
            transport_name="disabled",
            reason="bridge_disabled",
        )
        raise ToolInvocationError(
            "bridge_disabled",
            (
                "Unity bridge is disabled for this project. "
                "Enable it with init_xuunity_light_unity_mcp.sh --project-root <path> --enable-project "
                "and reopen Unity."
            ),
            {
                "request_submitted": False,
                "request_ownership_acquired": False,
                "transport_outcome": "request_not_submitted",
                "operation_outcome": "request_not_dispatched",
                "recommended_next_action": "enable_bridge_and_retry",
                "transport": "disabled",
            },
        )

    transport = resolve_bridge_transport(project_root)
    response, request_id, request_started_at = transport.invoke(
        project_root,
        operation,
        args,
        timeout_ms,
        post_reset_recovery_cap_ms=post_reset_recovery_cap_ms,
    )
    return response, request_id, request_started_at, transport.metadata(project_root)
