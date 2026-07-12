import json
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_bridge_transport
from server_bridge_journal import write_host_request_journal_event
from server_bridge_paths import response_path
from server_core import ToolInvocationError, write_json


def healthy_tcp_state(port: int) -> dict:
    return {
        "bridge_generation": 7,
        "bridge_session_id": "session-7",
        "transport": "tcp_loopback",
        "transport_listener_state": "listening",
        "transport_host": "127.0.0.1",
        "transport_port": port,
        "health_status": "healthy",
        "pending_request_count": 0,
    }


def read_request(connection: socket.socket) -> dict:
    chunks: list[bytes] = []
    while True:
        chunk = connection.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
    return json.loads(b"".join(chunks).decode("utf-8"))


class TcpTransportFramingTests(unittest.TestCase):
    def test_complete_json_frame_returns_without_waiting_for_socket_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(5.0)
            port = int(listener.getsockname()[1])
            keep_connection_open = threading.Event()
            server_error: list[BaseException] = []

            def serve() -> None:
                try:
                    connection, _ = listener.accept()
                    with connection:
                        request = read_request(connection)
                        response = json.dumps(
                            {
                                "request_id": request["request_id"],
                                "status": "ok",
                                "payload_type": "unity.status",
                                "payload_json": "{}",
                            },
                            indent=2,
                        ).encode("utf-8")
                        midpoint = max(1, len(response) // 2)
                        connection.sendall(response[:midpoint])
                        connection.sendall(response[midpoint:])
                        keep_connection_open.wait(3.0)
                except BaseException as exc:  # pragma: no cover - surfaced below
                    server_error.append(exc)

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            state = healthy_tcp_state(port)

            try:
                with (
                    mock.patch.object(server_bridge_transport, "try_read_bridge_state", return_value=state),
                    mock.patch.object(server_bridge_transport, "read_best_effort_bridge_state", return_value=state),
                ):
                    started = time.monotonic()
                    response, request_id, _ = server_bridge_transport.TcpLoopbackBridgeTransport().invoke(
                        project_root,
                        "unity.status",
                        {},
                        timeout_ms=2000,
                    )
                    elapsed = time.monotonic() - started
            finally:
                keep_connection_open.set()
                listener.close()
                thread.join(timeout=5.0)

            self.assertEqual("ok", response["status"])
            self.assertEqual(request_id, response["request_id"])
            self.assertLess(elapsed, 1.0, "a complete JSON frame must not wait for TCP EOF")
            self.assertEqual([], server_error)

    def test_tcp_missing_frame_recovers_file_outbox_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(5.0)
            port = int(listener.getsockname()[1])
            release_connection = threading.Event()
            server_error: list[BaseException] = []

            def serve() -> None:
                try:
                    connection, _ = listener.accept()
                    with connection:
                        request = read_request(connection)
                        request_id = str(request["request_id"])
                        write_host_request_journal_event(
                            project_root,
                            "request_started",
                            {
                                "request_id": request_id,
                                "operation": "unity.status",
                                "bridge_generation": 7,
                                "bridge_session_id": "session-7",
                            },
                        )
                        write_host_request_journal_event(
                            project_root,
                            "request_completed",
                            {
                                "request_id": request_id,
                                "operation": "unity.status",
                                "operation_status": "ok",
                                "bridge_generation": 7,
                                "bridge_session_id": "session-7",
                            },
                        )
                        write_json(
                            response_path(project_root, request_id),
                            {
                                "request_id": request_id,
                                "status": "ok",
                                "payload_type": "unity.status",
                                "payload_json": "{}",
                            },
                        )
                        release_connection.wait(3.0)
                except BaseException as exc:  # pragma: no cover - surfaced below
                    server_error.append(exc)

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            state = healthy_tcp_state(port)

            try:
                with (
                    mock.patch.object(server_bridge_transport, "try_read_bridge_state", return_value=state),
                    mock.patch.object(server_bridge_transport, "read_best_effort_bridge_state", return_value=state),
                ):
                    response, request_id, _ = server_bridge_transport.TcpLoopbackBridgeTransport().invoke(
                        project_root,
                        "unity.status",
                        {},
                        timeout_ms=250,
                    )
            finally:
                release_connection.set()
                listener.close()
                thread.join(timeout=5.0)

            self.assertEqual("ok", response["status"])
            self.assertEqual(request_id, response["request_id"])
            self.assertFalse(response_path(project_root, request_id).exists())
            self.assertEqual([], server_error)

    def test_tcp_reset_after_completion_recovers_file_outbox_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(5.0)
            port = int(listener.getsockname()[1])
            server_error: list[BaseException] = []

            def serve() -> None:
                try:
                    connection, _ = listener.accept()
                    request = read_request(connection)
                    request_id = str(request["request_id"])
                    write_host_request_journal_event(
                        project_root,
                        "request_started",
                        {
                            "request_id": request_id,
                            "operation": "unity.status",
                            "bridge_generation": 7,
                            "bridge_session_id": "session-7",
                        },
                    )
                    write_host_request_journal_event(
                        project_root,
                        "request_completed",
                        {
                            "request_id": request_id,
                            "operation": "unity.status",
                            "operation_status": "ok",
                            "bridge_generation": 7,
                            "bridge_session_id": "session-7",
                        },
                    )
                    write_json(
                        response_path(project_root, request_id),
                        {
                            "request_id": request_id,
                            "status": "ok",
                            "payload_type": "unity.status",
                            "payload_json": "{}",
                        },
                    )
                    linger_configured = False
                    for format_string in ("ii", "hh"):
                        try:
                            connection.setsockopt(
                                socket.SOL_SOCKET,
                                socket.SO_LINGER,
                                struct.pack(format_string, 1, 0),
                            )
                            linger_configured = True
                            break
                        except OSError:
                            continue
                    if not linger_configured:
                        raise OSError("could not configure abortive TCP close")
                    connection.close()
                except BaseException as exc:  # pragma: no cover - surfaced below
                    server_error.append(exc)

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            state = healthy_tcp_state(port)

            try:
                with (
                    mock.patch.object(server_bridge_transport, "try_read_bridge_state", return_value=state),
                    mock.patch.object(server_bridge_transport, "read_best_effort_bridge_state", return_value=state),
                ):
                    response, request_id, _ = server_bridge_transport.TcpLoopbackBridgeTransport().invoke(
                        project_root,
                        "unity.status",
                        {},
                        timeout_ms=2000,
                    )
            finally:
                listener.close()
                thread.join(timeout=5.0)

            self.assertEqual("ok", response["status"])
            self.assertEqual(request_id, response["request_id"])
            self.assertFalse(response_path(project_root, request_id).exists())
            self.assertEqual([], server_error)

    def test_tcp_send_failure_after_dispatch_is_not_reported_as_not_submitted(self) -> None:
        class FailingSendSocket:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def settimeout(self, timeout: float) -> None:
                return None

            def sendall(self, payload: bytes) -> None:
                raise ConnectionResetError("reset during send")

        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            state = healthy_tcp_state(43123)
            with (
                mock.patch.object(server_bridge_transport.socket, "create_connection", return_value=FailingSendSocket()),
                mock.patch.object(server_bridge_transport, "try_read_bridge_state", return_value=state),
                mock.patch.object(server_bridge_transport, "read_best_effort_bridge_state", return_value=state),
            ):
                with self.assertRaises(ToolInvocationError) as ctx:
                    server_bridge_transport.TcpLoopbackBridgeTransport().invoke(
                        project_root,
                        "unity.status",
                        {},
                        timeout_ms=250,
                    )

            self.assertEqual("transport_response_missing", ctx.exception.code)
            self.assertFalse(ctx.exception.details.get("automatic_retry_safe"))
            final_status = ctx.exception.details.get("request_final_status") or {}
            self.assertTrue(final_status.get("request_submitted"), final_status)

    def test_transport_restarting_retries_only_requests_not_started_by_unity(self) -> None:
        for request_started, expected_retryable in ((False, True), (True, False)):
            with self.subTest(request_started=request_started), tempfile.TemporaryDirectory() as tmp_dir:
                project_root = Path(tmp_dir)
                listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                port = int(listener.getsockname()[1])

                def serve() -> None:
                    connection, _ = listener.accept()
                    with connection:
                        request = read_request(connection)
                        request_id = str(request["request_id"])
                        if request_started:
                            write_host_request_journal_event(
                                project_root,
                                "request_started",
                                {
                                    "request_id": request_id,
                                    "operation": "unity.status",
                                    "bridge_generation": 7,
                                    "bridge_session_id": "session-7",
                                },
                            )
                        connection.sendall(
                            (
                                json.dumps(
                                    {
                                        "request_id": request_id,
                                        "status": "error",
                                        "error": {
                                            "code": "transport_restarting",
                                            "message": "bridge restarting",
                                        },
                                    },
                                    separators=(",", ":"),
                                )
                                + "\n"
                            ).encode("utf-8")
                        )

                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                state = healthy_tcp_state(port)
                try:
                    with (
                        mock.patch.object(server_bridge_transport, "try_read_bridge_state", return_value=state),
                        mock.patch.object(server_bridge_transport, "read_best_effort_bridge_state", return_value=state),
                    ):
                        started_at = time.monotonic()
                        with self.assertRaises(ToolInvocationError) as ctx:
                            server_bridge_transport.TcpLoopbackBridgeTransport().invoke(
                                project_root,
                                "unity.status",
                                {},
                                timeout_ms=300,
                            )
                        elapsed = time.monotonic() - started_at
                finally:
                    listener.close()
                    thread.join(timeout=5.0)

                self.assertEqual("request_lifecycle_reset", ctx.exception.code)
                self.assertEqual(expected_retryable, ctx.exception.details.get("retryable"))
                self.assertEqual(request_started, ctx.exception.details.get("request_processed"))
                self.assertLess(elapsed, 0.65, "recovery timeout budget must not be consumed twice")


class UnityTransportSourceContractTests(unittest.TestCase):
    def test_unity_tcp_responses_are_compact_newline_delimited_frames(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "packages"
            / "com.xuunity.light-mcp"
            / "Editor"
            / "Bridge"
            / "XUUnityLightMcpBridgeTransportRuntime.cs"
        ).read_text(encoding="utf-8")

        self.assertGreaterEqual(
            source.count("writer.WriteLine(JsonUtility.ToJson(response, false));"),
            2,
        )
        self.assertNotIn("writer.Write(JsonUtility.ToJson(response, true));", source)


if __name__ == "__main__":
    unittest.main()
