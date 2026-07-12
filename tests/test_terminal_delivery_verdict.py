import contextlib
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_bridge_final_status
import server_batch_orchestrator
import server_cli_bridge_commands
import server_mcp_tools
from server_core import ToolInvocationError, write_json


def healthy_state(generation: int, session_id: str) -> dict:
    return {
        "bridge_generation": generation,
        "bridge_session_id": session_id,
        "transport": "tcp_loopback",
        "transport_listener_state": "listening",
        "health_status": "healthy",
        "pending_request_count": 0,
    }


def write_event(journal_dir: Path, name: str, payload: dict) -> None:
    write_json(journal_dir / name, payload)


class TerminalDeliveryVerdictTests(unittest.TestCase):
    def _write_completed_request(self, project_root: Path, *, tracked: bool) -> tuple[Path, str]:
        request_id = "req-delivery-verdict"
        journal_dir = project_root / "Library" / "XUUnityLightMcp" / "journal" / "requests"
        write_event(
            journal_dir,
            "01_submitted.json",
            {
                "event_id": "01",
                "event_type": "request_submitted",
                "event_at_utc": "2026-07-12T10:00:00Z",
                "request_id": request_id,
                "operation": "unity.status",
                "bridge_generation": 4,
                "bridge_session_id": "session-4",
                "host_delivery_tracking": tracked,
            },
        )
        write_event(
            journal_dir,
            "02_started.json",
            {
                "event_id": "02",
                "event_type": "request_started",
                "event_at_utc": "2026-07-12T10:00:01Z",
                "request_id": request_id,
                "operation": "unity.status",
                "bridge_generation": 4,
                "bridge_session_id": "session-4",
            },
        )
        write_event(
            journal_dir,
            "03_completed.json",
            {
                "event_id": "03",
                "event_type": "request_completed",
                "event_at_utc": "2026-07-12T10:00:02Z",
                "request_id": request_id,
                "operation": "unity.status",
                "operation_status": "ok",
                "bridge_generation": 5,
                "bridge_session_id": "session-5",
            },
        )
        return journal_dir, request_id

    def test_completed_request_without_delivery_receipt_is_decision_grade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "Project With Spaces"
            _, request_id = self._write_completed_request(project_root, tracked=True)

            summary = server_bridge_final_status.build_request_final_status(
                project_root,
                request_id,
                current_state=healthy_state(5, "session-5"),
            )

        self.assertEqual("completed_ok", summary["operation_outcome"])
        self.assertEqual("unity_completed_confirmed", summary["result_trust_class"])
        self.assertEqual(
            "unity_completed_host_delivery_unproven",
            summary["terminal_disposition"],
        )
        self.assertEqual("unity_request_journal", summary["completion_source"])
        self.assertEqual(4, summary["submission_bridge_generation"])
        self.assertEqual(5, summary["completion_bridge_generation"])
        self.assertEqual(1, summary["bridge_generation_delta"])
        self.assertTrue(summary["host_delivery_unproven"])
        self.assertEqual("none", summary["recommended_next_action"])
        self.assertEqual("continue_without_retry", summary["safe_next_action"])
        self.assertFalse(summary["operator_verdict"]["should_retry"])
        self.assertIn(f'"{project_root}"', summary["recommended_recovery_command"])
        self.assertIn(f"--request-id {request_id}", summary["recommended_recovery_command"])

    def test_delivery_receipt_resolves_the_unproven_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            journal_dir, request_id = self._write_completed_request(project_root, tracked=True)
            write_event(
                journal_dir,
                "04_delivery.json",
                {
                    "event_id": "04",
                    "event_type": "request_delivery_observed",
                    "event_at_utc": "2026-07-12T10:00:03Z",
                    "request_id": request_id,
                    "operation": "unity.status",
                    "host_delivery_observed": True,
                    "host_delivery_source": "tcp_json_frame",
                    "bridge_generation": 5,
                    "bridge_session_id": "session-5",
                },
            )

            summary = server_bridge_final_status.build_request_final_status(
                project_root,
                request_id,
                current_state=healthy_state(5, "session-5"),
            )

        self.assertEqual("unity_completed_host_delivery_observed", summary["terminal_disposition"])
        self.assertTrue(summary["host_delivery_observed"])
        self.assertFalse(summary["host_delivery_unproven"])
        self.assertEqual("tcp_json_frame", summary["host_delivery_source"])
        self.assertEqual("confirmed_success", summary["operator_verdict"]["status"])

    def test_legacy_submission_is_not_retroactively_called_delivery_unproven(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            _, request_id = self._write_completed_request(project_root, tracked=False)

            summary = server_bridge_final_status.build_request_final_status(
                project_root,
                request_id,
                current_state=healthy_state(5, "session-5"),
            )

        self.assertFalse(summary["host_delivery_tracking"])
        self.assertFalse(summary["host_delivery_unproven"])
        self.assertEqual("", summary["terminal_disposition"])
        self.assertEqual("confirmed_success", summary["operator_verdict"]["status"])

    def test_transport_error_keeps_compact_delivery_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            _, request_id = self._write_completed_request(project_root, tracked=True)

            error = server_bridge_final_status.build_transport_response_missing_tool_error(
                project_root,
                request_id=request_id,
                operation="unity.status",
                transport="tcp_loopback",
                current_state=healthy_state(5, "session-5"),
                poll_timeout_ms=0,
            )

        compact = error.details["request_final_status"]
        self.assertEqual("transport_response_missing", error.code)
        self.assertEqual("unity_completed_host_delivery_unproven", compact["terminal_disposition"])
        self.assertEqual("unity_request_journal", compact["completion_source"])
        self.assertEqual(1, compact["bridge_generation_delta"])
        self.assertEqual("continue_without_retry", compact["safe_next_action"])
        self.assertFalse(compact["operator_verdict"]["should_retry"])

    def test_completion_clears_historical_reclassification_retryability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            journal_dir, request_id = self._write_completed_request(project_root, tracked=True)
            write_event(
                journal_dir,
                "02_reclassified.json",
                {
                    "event_id": "02-reclassified",
                    "event_type": "request_reclassified",
                    "event_at_utc": "2026-07-12T10:00:01Z",
                    "request_id": request_id,
                    "operation": "unity.status",
                    "reclassified_status": "retryable_after_lifecycle_reset",
                    "retryable": True,
                    "bridge_generation": 5,
                    "bridge_session_id": "session-5",
                },
            )

            summary = server_bridge_final_status.build_request_final_status(
                project_root,
                request_id,
                current_state=healthy_state(5, "session-5"),
            )

        self.assertEqual("completed_ok", summary["operation_outcome"])
        self.assertTrue(summary["reclassification_retryable"])
        self.assertFalse(summary["retryable"])
        self.assertFalse(summary["operator_verdict"]["should_retry"])

    def test_delivery_is_pending_until_deadline_or_explicit_channel_loss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            journal_dir, request_id = self._write_completed_request(project_root, tracked=True)
            write_event(
                journal_dir,
                "01_submitted.json",
                {
                    "event_id": "01",
                    "event_type": "request_submitted",
                    "event_at_utc": "2026-07-12T10:00:00Z",
                    "request_id": request_id,
                    "operation": "unity.status",
                    "bridge_generation": 4,
                    "bridge_session_id": "session-4",
                    "host_delivery_tracking": True,
                    "request_timeout_ms": 60000,
                    "request_submitted_unix": time.time(),
                },
            )

            pending = server_bridge_final_status.build_request_final_status(
                project_root,
                request_id,
                current_state=healthy_state(5, "session-5"),
            )
            write_event(
                journal_dir,
                "04_delivery_unproven.json",
                {
                    "event_id": "04",
                    "event_type": "request_delivery_unproven",
                    "event_at_utc": "2026-07-12T10:00:03Z",
                    "request_id": request_id,
                    "operation": "unity.status",
                    "host_delivery_observed": False,
                    "reason": "response_channel_reset_before_host_delivery",
                },
            )
            unproven = server_bridge_final_status.build_request_final_status(
                project_root,
                request_id,
                current_state=healthy_state(5, "session-5"),
            )

        self.assertTrue(pending["host_delivery_pending"])
        self.assertFalse(pending["host_delivery_unproven"])
        self.assertFalse(pending["delivery_deadline_elapsed"])
        self.assertEqual("", pending["terminal_disposition"])
        self.assertFalse(unproven["host_delivery_pending"])
        self.assertTrue(unproven["host_delivery_unproven"])
        self.assertEqual(
            "unity_completed_host_delivery_unproven",
            unproven["terminal_disposition"],
        )


class FinalStatusMcpProjectionTests(unittest.TestCase):
    def test_mcp_final_status_is_compact_by_default_and_full_on_request(self) -> None:
        full = {
            "request_id": "req-1",
            "operation": "unity.status",
            "request_submitted": True,
            "request_started": True,
            "request_completed": True,
            "request_observed_in_unity_journal": True,
            "operation_outcome": "completed_ok",
            "result_trust_class": "unity_completed_confirmed",
            "terminal_disposition": "unity_completed_host_delivery_unproven",
            "completion_source": "unity_request_journal",
            "host_delivery_tracking": True,
            "host_delivery_observed": False,
            "host_delivery_unproven": True,
            "safe_next_action": "continue_without_retry",
            "submission_bridge_generation": 4,
            "completion_bridge_generation": 5,
            "current_bridge_generation": 5,
            "bridge_generation_delta": 1,
            "recommended_next_action": "none",
            "operator_verdict": {
                "status": "unity_completed_host_delivery_unproven",
                "should_retry": False,
                "next_action": "continue_without_retry",
            },
            "journal_event_paths": ["private/path.json"],
            "artifact_manifest": {"large": True},
        }

        def build_summary(*_args):
            return dict(full)

        compact_result = server_mcp_tools.call_unity_request_final_status_tool(
            {"projectRoot": "/tmp/project", "requestId": "req-1"},
            ensure_project_root=lambda value: Path(value),
            build_request_final_status_summary=build_summary,
        )
        full_result = server_mcp_tools.call_unity_request_final_status_tool(
            {
                "projectRoot": "/tmp/project",
                "requestId": "req-1",
                "includeFullPayload": True,
            },
            ensure_project_root=lambda value: Path(value),
            build_request_final_status_summary=build_summary,
        )

        compact = compact_result["structuredContent"]
        self.assertEqual("compact_final_status", compact["payload_mode"])
        self.assertEqual("unity_completed_host_delivery_unproven", compact["terminal_disposition"])
        self.assertNotIn("journal_event_paths", compact)
        self.assertNotIn("artifact_manifest", compact)
        self.assertEqual(full, full_result["structuredContent"])
        self.assertEqual(compact, json.loads(compact_result["content"][0]["text"]))

    def test_cli_final_status_is_compact_by_default_and_full_on_request(self) -> None:
        full = {
            "request_id": "req-cli",
            "operation": "unity.status",
            "request_submitted": True,
            "request_started": True,
            "request_completed": True,
            "request_observed_in_unity_journal": True,
            "operation_outcome": "completed_ok",
            "result_trust_class": "unity_completed_confirmed",
            "recommended_next_action": "none",
            "journal_event_paths": ["full-only.json"],
        }

        def invoke(include_full_payload: bool) -> dict:
            stdout = io.StringIO()
            args = SimpleNamespace(
                project_root="/tmp/project",
                request_id="req-cli",
                operation="unity.status",
                timeout_ms=0,
                include_full_payload=include_full_payload,
            )
            with (
                mock.patch.object(
                    server_cli_bridge_commands,
                    "ensure_project_root",
                    return_value=Path("/tmp/project"),
                ),
                mock.patch.object(
                    server_cli_bridge_commands,
                    "build_request_final_status_from_context",
                    return_value=dict(full),
                ),
                contextlib.redirect_stdout(stdout),
            ):
                server_cli_bridge_commands.cmd_request_final_status(args)
            return json.loads(stdout.getvalue())

        compact = invoke(False)
        verbose = invoke(True)

        self.assertEqual("compact_final_status", compact["payload_mode"])
        self.assertNotIn("journal_event_paths", compact)
        self.assertEqual(full, verbose)

    def test_cli_latest_status_no_match_is_still_compact(self) -> None:
        stdout = io.StringIO()
        args = SimpleNamespace(
            project_root="/tmp/project",
            operation=["unity.status"],
            timeout_ms=0,
            include_full_payload=False,
        )
        with (
            mock.patch.object(
                server_cli_bridge_commands,
                "ensure_project_root",
                return_value=Path("/tmp/project"),
            ),
            mock.patch.object(
                server_cli_bridge_commands,
                "current_project_context_bridge_state",
                return_value=healthy_state(2, "session-2"),
            ),
            mock.patch.object(
                server_cli_bridge_commands,
                "find_latest_request_event",
                return_value=None,
            ),
            mock.patch.object(
                server_cli_bridge_commands,
                "apply_discovery_to_final_status_summary",
                side_effect=lambda summary, _root: summary,
            ),
            contextlib.redirect_stdout(stdout),
        ):
            server_cli_bridge_commands.cmd_request_latest_status(args)

        compact = json.loads(stdout.getvalue())
        self.assertEqual("compact_final_status", compact["payload_mode"])
        self.assertFalse(compact["lookup_found"])
        self.assertEqual(["unity.status"], compact["matched_operations"])
        self.assertNotIn("journal_event_paths", compact)


class LifecycleRetrySafetyTests(unittest.TestCase):
    def test_processed_lifecycle_reset_is_not_automatically_retried(self) -> None:
        project_root = Path("/tmp/lifecycle-retry-project")
        context = SimpleNamespace(project_root=project_root)
        error = ToolInvocationError(
            "request_lifecycle_reset",
            "response channel reset",
            {"retryable": False, "request_processed": True},
        )
        policy = {
            "activate_unity": False,
            "wait_for_idle_before": False,
            "wait_for_idle_after": False,
            "idle_stable_cycles_after": 1,
            "retry_on_lifecycle_reset": True,
            "retry_on_transport_response_missing": False,
            "retry_on_transport_connect_failed": False,
            "post_reset_recovery_cap_ms": 0,
        }

        with (
            mock.patch.object(server_batch_orchestrator, "get_project_context", return_value=context),
            mock.patch.object(
                server_batch_orchestrator,
                "run_in_project_request_lock",
                side_effect=lambda _context, _operation, callback: callback(),
            ),
            mock.patch.object(
                server_batch_orchestrator,
                "resolve_operation_lifecycle_policy",
                return_value=policy,
            ),
            mock.patch.object(server_batch_orchestrator, "try_read_live_editor_state", return_value={}),
            mock.patch.object(
                server_batch_orchestrator,
                "current_project_context_bridge_state",
                return_value={},
            ),
            mock.patch.object(server_batch_orchestrator, "fail_if_compile_broken_for_operation"),
            mock.patch.object(
                server_batch_orchestrator,
                "invoke_bridge_transport",
                side_effect=error,
            ) as invoke_transport,
            mock.patch.object(
                server_batch_orchestrator,
                "recover_project_bridge_for_reconciliation",
            ) as recover,
            mock.patch.object(
                server_batch_orchestrator,
                "enrich_tool_invocation_error_with_discovery",
                side_effect=lambda _root, exc: exc,
            ),
        ):
            with self.assertRaises(ToolInvocationError) as ctx:
                server_batch_orchestrator.invoke_bridge(
                    str(project_root),
                    "unity.status",
                    {},
                    1000,
                )

        self.assertIs(error, ctx.exception)
        self.assertEqual(1, invoke_transport.call_count)
        recover.assert_not_called()


if __name__ == "__main__":
    unittest.main()
