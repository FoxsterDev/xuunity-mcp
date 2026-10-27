from __future__ import annotations

import json
import sys
from typing import Any, Callable
from server_host_call_timing import (
    emit_host_call_timing_receipt, host_call_timing_scope, measure_host_stage,
)


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def success_response(request_id: Any, result: Any) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def error_response(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if data is not None:
        payload["error"]["data"] = data
    return payload


def emit_message(message: dict[str, Any]) -> None:
    with measure_host_stage("serialization"):
        encoded = json.dumps(message, ensure_ascii=True, separators=(",", ":")) + "\n"
    try:
        sys.stdout.write(encoded)
        sys.stdout.flush()
    except Exception:
        emit_host_call_timing_receipt("stdout_emission_failed", "failed")
        raise
    emit_host_call_timing_receipt("stdout_flush_returned")


def log_stderr(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def build_initialize_result(
    requested_version: str | None,
    *,
    protocol_version: str,
    server_info: dict[str, Any],
) -> dict[str, Any]:
    negotiated_version = requested_version or protocol_version
    if negotiated_version != protocol_version:
        negotiated_version = protocol_version

    return {
        "protocolVersion": negotiated_version,
        "capabilities": {
            "tools": {
                "listChanged": False,
            }
        },
        "serverInfo": server_info,
        "instructions": (
            "Use these tools for Unity editor validation over a lightweight file-IPC bridge. "
            "Every tool requires an explicit projectRoot."
        ),
    }


def list_tools_result(tools: dict[str, dict[str, Any]]) -> dict[str, Any]:
    tool_list = []
    for name, spec in tools.items():
        tool_list.append(
            {
                "name": name,
                "title": name.replace("_", " ").title(),
                "description": spec["description"],
                "inputSchema": spec["inputSchema"],
            }
        )
    return {"tools": tool_list}


def handle_json_rpc_message(
    message: dict[str, Any],
    session: dict[str, Any],
    *,
    protocol_version: str,
    server_info: dict[str, Any],
    tools: dict[str, dict[str, Any]],
    call_tool: Callable[[str, dict[str, Any] | None], dict[str, Any]],
) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if method == "initialize":
        if not isinstance(params, dict):
            raise JsonRpcError(-32602, "initialize params must be an object.")
        requested_version = params.get("protocolVersion")
        session["initialized"] = False
        session["protocolVersion"] = protocol_version
        return success_response(
            request_id,
            build_initialize_result(
                requested_version,
                protocol_version=protocol_version,
                server_info=server_info,
            ),
        )

    if method == "notifications/initialized":
        session["initialized"] = True
        return None

    if method == "ping":
        return success_response(request_id, {})

    if method == "tools/list":
        return success_response(request_id, list_tools_result(tools))

    if method == "tools/call":
        with host_call_timing_scope("direct_handler") as timing:
            if timing is not None:
                timing.request_id = (
                    request_id if isinstance(request_id, (int, float, type(None))) else str(request_id)[:80]
                )
                timing.tool_name = (
                    str(params.get("name") or "tools/call")[:80] if isinstance(params, dict) else "tools/call"
                )
            result = _call_tool_result(params, call_tool)
            if timing is not None:
                result = dict(result)
                result["_meta"] = {
                    **result.get("_meta", {}),
                    "xuunity_host_timing": timing.snapshot("before_response_serialization"),
                }
            return success_response(request_id, result)

    raise JsonRpcError(-32601, f"Method not found: {method}")


def _call_tool_result(params: Any, call_tool: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise JsonRpcError(-32602, "tools/call params must be an object.")
    name = params.get("name")
    arguments = params.get("arguments")
    if not isinstance(name, str) or not name:
        raise JsonRpcError(-32602, "tools/call requires a non-empty tool name.")
    if arguments is not None and not isinstance(arguments, dict):
        raise JsonRpcError(-32602, "tools/call arguments must be an object when provided.")
    return call_tool(name, arguments)


def serve_stdio(
    *,
    protocol_version: str,
    handle_message: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None],
) -> int:
    session = {"initialized": False, "protocolVersion": protocol_version}
    for raw_line in sys.stdin:
        with host_call_timing_scope("stdio_received_line"):
            _serve_line(raw_line, session, handle_message)

    return 0


def _serve_line(raw_line: str, session: dict[str, Any], handle_message: Callable[..., Any]) -> None:
    line = raw_line.strip()
    if not line:
        return

    message = None
    try:
        message = json.loads(line)
        if not isinstance(message, dict):
            raise JsonRpcError(-32600, "Invalid JSON-RPC message.")

        response = handle_message(message, session)
        if response is not None:
            emit_message(response)
    except json.JSONDecodeError:
        emit_message(error_response(None, -32700, "Parse error"))
    except JsonRpcError as exc:
        msg_id = message.get("id") if isinstance(message, dict) else None
        emit_message(error_response(msg_id, exc.code, exc.message, exc.data))
    except Exception as exc:
        log_stderr(f"[xuunity-mcp] internal error: {exc}")
        msg_id = message.get("id") if isinstance(message, dict) else None
        emit_message(error_response(msg_id, -32603, "Internal error"))
