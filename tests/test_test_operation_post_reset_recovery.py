import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_batch_orchestrator
import server_bridge_final_status
import server_bridge_runtime
import server_bridge_transport
import server_runtime_config
import server_specs
from server_bridge_journal import read_request_journal_events, write_host_request_journal_event
from server_bridge_paths import response_path
from server_core import ToolInvocationError, read_json, write_json


TEST_OPERATIONS = {"unity.tests.run_editmode", "unity.tests.run_playmode"}


def healthy_tcp_state(port: int, generation: int = 7) -> dict:
    return {
        "bridge_generation": generation,
        "bridge_session_id": f"session-{generation}",
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


def transport_restarting_frame(request_id: str) -> bytes:
    return (
        json.dumps(
            {
                "request_id": request_id,
                "status": "error",
                "error": {"code": "transport_restarting", "message": "bridge restarting"},
            },
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def journal_event(project_root: Path, event_type: str, request_id: str, operation: str, **extra: object) -> None:
    write_host_request_journal_event(
        project_root,
        event_type,
        {
            "request_id": request_id,
            "operation": operation,
            "bridge_generation": 7,
            "bridge_session_id": "session-7",
            **extra,
        },
    )


def events_of_type(project_root: Path, request_id: str, event_type: str) -> list[dict]:
    return [
        event
        for event in read_request_journal_events(project_root, request_id)
        if str(event.get("event_type") or "") == event_type
    ]


class ShippedPolicyTests(unittest.TestCase):
    def test_shipped_test_policies_have_no_post_reset_cap(self) -> None:
        self.assertEqual(TEST_OPERATIONS, set(server_specs.CALLER_DEADLINE_RECOVERY_OPERATIONS))
        for operation in TEST_OPERATIONS:
            policy = server_specs.OPERATION_LIFECYCLE_POLICIES[operation]
            self.assertNotIn("post_reset_recovery_cap_ms", policy)
            self.assertTrue(policy["post_reset_recovery_caller_deadline"])

        defaults = read_json(server_runtime_config.runtime_defaults_path())
        for operation in TEST_OPERATIONS:
            settings = defaults["operations"][operation]
            self.assertNotIn("post_reset_recovery_cap_ms", settings)
            self.assertEqual(300000, settings["default_timeout_ms"])
        self.assertEqual(180000, defaults["operations"]["unity.project.refresh"]["post_reset_recovery_cap_ms"])


class RuntimeOverrideTests(unittest.TestCase):
    def override_sources(self, tmp_root: Path):
        override_path = tmp_root / "runtime_override.json"
        write_json(
            override_path,
            {
                "operations": {
                    "unity.tests.run_playmode": {"post_reset_recovery_cap_ms": 300000},
                    "unity.project.refresh": {"post_reset_recovery_cap_ms": 120000},
                }
            },
        )
        return mock.patch.object(
            server_runtime_config,
            "runtime_config_sources",
            return_value=[server_runtime_config.runtime_defaults_path(), override_path],
        )

    def test_runtime_override_cannot_reimpose_cap_on_test_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            with self.override_sources(tmp_root):
                playmode = server_batch_orchestrator.resolve_operation_lifecycle_policy(
                    tmp_root, "unity.tests.run_playmode"
                )
                editmode = server_batch_orchestrator.resolve_operation_lifecycle_policy(
                    tmp_root, "unity.tests.run_editmode"
                )
                refresh = server_batch_orchestrator.resolve_operation_lifecycle_policy(
                    tmp_root, "unity.project.refresh"
                )

        self.assertEqual(0, playmode["post_reset_recovery_cap_ms"])
        self.assertEqual(300000, playmode["post_reset_recovery_ignored_override_cap_ms"])
        self.assertTrue(playmode["post_reset_recovery_caller_deadline"])
        self.assertEqual(0, editmode["post_reset_recovery_cap_ms"])
        self.assertEqual(0, editmode["post_reset_recovery_ignored_override_cap_ms"])
        self.assertEqual(120000, refresh["post_reset_recovery_cap_ms"])
        self.assertEqual(0, refresh["post_reset_recovery_ignored_override_cap_ms"])
        self.assertFalse(refresh["post_reset_recovery_caller_deadline"])

    def test_runtime_config_report_lists_ignored_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            with self.override_sources(tmp_root):
                report = server_runtime_config.build_runtime_config_report(tmp_root)

        self.assertEqual(
            [
                {
                    "operation": "unity.tests.run_playmode",
                    "key": "post_reset_recovery_cap_ms",
                    "value": 300000,
                    "reason": "test_operations_wait_for_caller_deadline",
                }
            ],
            report["ignored_overrides"],
        )


class LifecycleSurfaceTests(unittest.TestCase):
    def invoke_with_policy(self, policy: dict, transport_response: dict | None = None) -> dict:
        return self.invoke_response_with_policy(policy, transport_response)["_xuunity_lifecycle"]

    def invoke_response_with_policy(self, policy: dict, transport_response: dict | None = None) -> dict:
        project_root = Path(tempfile.gettempdir()) / "post-reset-lifecycle-project"
        context = SimpleNamespace(project_root=project_root)
        with (
            mock.patch.object(server_batch_orchestrator, "get_project_context", return_value=context),
            mock.patch.object(
                server_batch_orchestrator,
                "run_in_project_request_lock",
                side_effect=lambda _context, _operation, callback: callback(),
            ),
            mock.patch.object(server_batch_orchestrator, "resolve_operation_lifecycle_policy", return_value=policy),
            mock.patch.object(server_batch_orchestrator, "try_read_live_editor_state", return_value={}),
            mock.patch.object(server_batch_orchestrator, "current_project_context_bridge_state", return_value={}),
            mock.patch.object(
                server_batch_orchestrator,
                "invoke_bridge_transport",
                return_value=(
                    transport_response or {"status": "ok", "payload_json": ""},
                    "req-1",
                    time.time(),
                    {"name": "tcp_loopback"},
                ),
            ),
            mock.patch.object(server_batch_orchestrator, "refresh_project_context"),
        ):
            return server_batch_orchestrator.invoke_bridge(str(project_root), "unity.status", {}, 1000)

    def base_policy(self) -> dict:
        return {
            "activate_unity": False,
            "wait_for_idle_before": False,
            "wait_for_idle_after": False,
            "idle_stable_cycles_after": 1,
            "retry_on_lifecycle_reset": False,
            "retry_on_transport_response_missing": False,
            "retry_on_transport_connect_failed": False,
        }

    def test_lifecycle_reports_caller_deadline_mode_and_ignored_override(self) -> None:
        lifecycle = self.invoke_with_policy(
            {
                **self.base_policy(),
                "post_reset_recovery_cap_ms": 0,
                "post_reset_recovery_caller_deadline": True,
                "post_reset_recovery_ignored_override_cap_ms": 300000,
            }
        )
        self.assertEqual("caller_deadline", lifecycle["post_reset_recovery_mode"])
        self.assertEqual(300000, lifecycle["post_reset_recovery_ignored_override_cap_ms"])

    def test_recovered_success_reports_budget_elapsed_and_completed_stop_reason(self) -> None:
        response = self.invoke_response_with_policy(
            {**self.base_policy(), "post_reset_recovery_cap_ms": 0, "post_reset_recovery_caller_deadline": True},
            {
                "status": "ok",
                "payload_json": "",
                "_xuunity_post_reset_recovery": {
                    "post_reset_recovery_mode": "caller_deadline",
                    "post_reset_recovery_budget_ms": 1199000,
                    "post_reset_recovery_elapsed_ms": 4200,
                    "post_reset_recovery_stop_reason": "completed",
                },
            },
        )

        lifecycle = response["_xuunity_lifecycle"]
        self.assertEqual("caller_deadline", lifecycle["post_reset_recovery_mode"])
        self.assertEqual(1199000, lifecycle["post_reset_recovery_budget_ms"])
        self.assertEqual(4200, lifecycle["post_reset_recovery_elapsed_ms"])
        self.assertEqual("completed", lifecycle["post_reset_recovery_stop_reason"])
        self.assertNotIn("_xuunity_post_reset_recovery", response)

        plain = self.invoke_with_policy({**self.base_policy(), "post_reset_recovery_cap_ms": 0})
        for key in ("post_reset_recovery_budget_ms", "post_reset_recovery_elapsed_ms", "post_reset_recovery_stop_reason"):
            self.assertNotIn(key, plain)

    def test_lifecycle_reports_capped_mode_without_ignored_override(self) -> None:
        lifecycle = self.invoke_with_policy({**self.base_policy(), "post_reset_recovery_cap_ms": 180000})
        self.assertEqual("capped", lifecycle["post_reset_recovery_mode"])
        self.assertNotIn("post_reset_recovery_ignored_override_cap_ms", lifecycle)


class TransportRestartingRecoveryTests(unittest.TestCase):
    def run_transport_restarting(
        self,
        project_root: Path,
        operation: str,
        *,
        timeout_ms: int,
        post_reset_recovery_cap_ms: int,
        complete_after_seconds: float | None = None,
        outbox_after_seconds: float | None = None,
        state_after_recovery: dict | None = None,
    ) -> tuple[object, float]:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(5.0)
        port = int(listener.getsockname()[1])
        state_holder = {"state": healthy_tcp_state(port)}
        workers: list[threading.Thread] = []

        def finish_run(request_id: str) -> None:
            if complete_after_seconds is None:
                return
            time.sleep(complete_after_seconds)
            journal_event(project_root, "request_completed", request_id, operation, operation_status="ok")
            if outbox_after_seconds is None:
                return
            time.sleep(max(0.0, outbox_after_seconds - complete_after_seconds))
            write_json(
                response_path(project_root, request_id),
                {"request_id": request_id, "status": "ok", "payload_type": operation, "payload_json": "{}"},
            )

        def serve() -> None:
            connection, _ = listener.accept()
            with connection:
                request = read_request(connection)
                request_id = str(request["request_id"])
                journal_event(project_root, "request_started", request_id, operation)
                worker = threading.Thread(target=finish_run, args=(request_id,), daemon=True)
                workers.append(worker)
                worker.start()
                connection.sendall(transport_restarting_frame(request_id))

        real_recover = server_bridge_transport.try_recover_completed_response_after_reset

        def recover_then_advance_state(*args, **kwargs):
            result = real_recover(*args, **kwargs)
            if state_after_recovery is not None:
                state_holder["state"] = state_after_recovery
            return result

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        result: object
        try:
            with (
                mock.patch.object(
                    server_bridge_transport, "try_read_bridge_state", side_effect=lambda _root: state_holder["state"]
                ),
                mock.patch.object(
                    server_bridge_transport,
                    "read_best_effort_bridge_state",
                    side_effect=lambda _root: state_holder["state"],
                ),
                mock.patch.object(
                    server_bridge_transport,
                    "try_recover_completed_response_after_reset",
                    side_effect=recover_then_advance_state,
                ),
            ):
                started_at = time.monotonic()
                try:
                    result = server_bridge_transport.TcpLoopbackBridgeTransport().invoke(
                        project_root,
                        operation,
                        {},
                        timeout_ms=timeout_ms,
                        post_reset_recovery_cap_ms=post_reset_recovery_cap_ms,
                    )
                except ToolInvocationError as exc:
                    result = exc
                elapsed = time.monotonic() - started_at
        finally:
            listener.close()
            thread.join(timeout=5.0)
            for worker in workers:
                worker.join(timeout=10.0)
        return result, elapsed

    def test_transport_restarting_waits_for_caller_deadline_and_returns_late_outbox_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            result, _ = self.run_transport_restarting(
                project_root,
                "unity.tests.run_playmode",
                timeout_ms=6000,
                post_reset_recovery_cap_ms=0,
                complete_after_seconds=1.0,
                outbox_after_seconds=1.3,
            )

            self.assertIsInstance(result, tuple, result)
            response, request_id, _ = result
            self.assertEqual("ok", response["status"])
            self.assertFalse(response_path(project_root, request_id).exists())
            self.assertEqual([], events_of_type(project_root, request_id, "request_reclassified"))
            delivery_sources = [
                str(event.get("host_delivery_source") or "")
                for event in events_of_type(project_root, request_id, "request_delivery_observed")
            ]
            self.assertIn("file_outbox_recovery_after_transport_restart", delivery_sources)
            recovery = response["_xuunity_post_reset_recovery"]
            self.assertEqual("caller_deadline", recovery["post_reset_recovery_mode"])
            self.assertEqual("completed", recovery["post_reset_recovery_stop_reason"])
            self.assertGreater(recovery["post_reset_recovery_budget_ms"], 0)
            self.assertLessEqual(recovery["post_reset_recovery_budget_ms"], 6000)
            self.assertGreaterEqual(recovery["post_reset_recovery_elapsed_ms"], 900)

    def test_recovery_reset_reports_mode_budget_and_stop_reason(self) -> None:
        cases = (
            ("unity.project.refresh", 2000, 400, "capped"),
            ("unity.tests.run_playmode", 1000, 0, "caller_deadline"),
        )
        for operation, timeout_ms, cap_ms, expected_mode in cases:
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp_dir:
                project_root = Path(tmp_dir)
                result, elapsed = self.run_transport_restarting(
                    project_root,
                    operation,
                    timeout_ms=timeout_ms,
                    post_reset_recovery_cap_ms=cap_ms,
                    state_after_recovery=healthy_tcp_state(0, generation=8),
                )

                self.assertIsInstance(result, ToolInvocationError, result)
                details = result.details
                self.assertEqual("request_lifecycle_reset", result.code)
                self.assertTrue(details["request_processed"])
                self.assertFalse(details["retryable"])
                self.assertEqual(expected_mode, details["post_reset_recovery_mode"])
                self.assertEqual("recovery_budget_elapsed", details["post_reset_recovery_stop_reason"])
                budget_ms = details["post_reset_recovery_budget_ms"]
                self.assertGreater(budget_ms, 0)
                self.assertLessEqual(budget_ms, cap_ms or timeout_ms)
                self.assertGreaterEqual(details["post_reset_recovery_elapsed_ms"], 0)
                self.assertNotIn(
                    "post_reset_recovery_stop_reason", details["request_final_status"]
                )
                self.assertLess(elapsed, 10.0)

                reclassified = events_of_type(project_root, details["request_id"], "request_reclassified")
                self.assertEqual(1, len(reclassified))
                self.assertEqual(expected_mode, reclassified[0]["post_reset_recovery_mode"])
                self.assertEqual("recovery_budget_elapsed", reclassified[0]["post_reset_recovery_stop_reason"])
                self.assertEqual(budget_ms, reclassified[0]["post_reset_recovery_budget_ms"])
                self.assertEqual(8, reclassified[0]["bridge_generation"])
                self.assertEqual(8, details["current_bridge_generation"])


class CompletedResponsePickupTests(unittest.TestCase):
    def seed_completed_request(self, project_root: Path, request_id: str, operation: str) -> None:
        journal_event(project_root, "request_submitted", request_id, operation)
        journal_event(project_root, "request_started", request_id, operation)
        journal_event(project_root, "request_completed", request_id, operation, operation_status="ok")

    def delayed_outbox_writer(self, project_root: Path, request_id: str, delay_seconds: float) -> threading.Thread:
        def write_later() -> None:
            time.sleep(delay_seconds)
            write_json(response_path(project_root, request_id), {"request_id": request_id, "status": "ok"})

        writer = threading.Thread(target=write_later, daemon=True)
        writer.start()
        return writer

    def test_completion_journaled_before_outbox_write_is_recovered(self) -> None:
        recoverers = (
            ("final_status", server_bridge_final_status.try_recover_completed_response_after_reset),
            ("facade", server_bridge_runtime.try_recover_completed_response_after_reset),
        )
        for label, recover in recoverers:
            with self.subTest(recoverer=label), tempfile.TemporaryDirectory() as tmp_dir:
                project_root = Path(tmp_dir)
                request_id = f"req-late-outbox-{label}"
                self.seed_completed_request(project_root, request_id, "unity.tests.run_playmode")
                writer = self.delayed_outbox_writer(project_root, request_id, 0.3)
                try:
                    response, final_status = recover(
                        project_root,
                        request_id=request_id,
                        operation="unity.tests.run_playmode",
                        current_state={},
                        poll_timeout_ms=0,
                    )
                finally:
                    writer.join(timeout=5.0)

                self.assertIsNotNone(response)
                self.assertEqual("ok", response["status"])
                self.assertEqual("completed", final_status["post_reset_recovery_stop_reason"])
                self.assertGreaterEqual(final_status["post_reset_recovery_elapsed_ms"], 0)
                self.assertFalse(response_path(project_root, request_id).exists())

    def test_non_test_operation_keeps_single_pickup_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            request_id = "req-refresh-no-outbox"
            self.seed_completed_request(project_root, request_id, "unity.project.refresh")
            writer = self.delayed_outbox_writer(project_root, request_id, 1.5)
            try:
                started_at = time.monotonic()
                response, final_status = server_bridge_final_status.try_recover_completed_response_after_reset(
                    project_root,
                    request_id=request_id,
                    operation="unity.project.refresh",
                    current_state={},
                    poll_timeout_ms=0,
                )
                elapsed = time.monotonic() - started_at
            finally:
                writer.join(timeout=5.0)

            self.assertIsNone(response)
            self.assertEqual("completed", final_status["post_reset_recovery_stop_reason"])
            self.assertLess(elapsed, 1.5)

    def test_long_caller_deadline_waits_poll_once_per_second(self) -> None:
        cases = (
            ("unity.tests.run_playmode", 120000, 1000),
            ("unity.tests.run_editmode", 30000, 200),
            ("unity.project.refresh", 120000, 200),
        )
        for operation, budget_ms, expected_interval_ms in cases:
            with self.subTest(operation=operation, budget_ms=budget_ms):
                with mock.patch.object(
                    server_bridge_final_status,
                    "build_request_final_status",
                    return_value={"request_completed": False, "recovery_gap_detected": True},
                ) as build_status:
                    response, final_status = server_bridge_final_status.try_recover_completed_response_after_reset(
                        Path(tempfile.gettempdir()),
                        request_id="req-interval",
                        operation=operation,
                        current_state={},
                        poll_timeout_ms=budget_ms,
                    )

                self.assertIsNone(response)
                self.assertEqual("recovery_gap_detected", final_status["post_reset_recovery_stop_reason"])
                kwargs = build_status.call_args.kwargs
                self.assertEqual(budget_ms, kwargs["poll_timeout_ms"])
                self.assertEqual(expected_interval_ms, kwargs["poll_interval_ms"])
                self.assertFalse(kwargs["return_reclassified_terminal_immediately"])


class LifecycleResetErrorFieldsTests(unittest.TestCase):
    def test_reset_error_omits_recovery_fields_for_existing_callers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            error = server_bridge_final_status.build_lifecycle_reset_tool_error(
                project_root,
                request_id="req-old-caller",
                operation="unity.status",
                transport="tcp_loopback",
                initial_bridge_generation=1,
                initial_bridge_session_id="s1",
                current_state={},
                poll_timeout_ms=0,
            )
        for key in (
            "post_reset_recovery_mode",
            "post_reset_recovery_budget_ms",
            "post_reset_recovery_elapsed_ms",
            "post_reset_recovery_stop_reason",
        ):
            self.assertNotIn(key, error.details)


if __name__ == "__main__":
    unittest.main()
