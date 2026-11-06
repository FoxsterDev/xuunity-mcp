import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server
import server_batch_orchestrator
from server_bridge_final_status import build_test_verdict_summary
from server_bridge_journal import read_request_journal_events
from server_mcp_protocol import JsonRpcError


def _call(arguments):
    return server.handle_json_rpc_message(
        {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "unity_tests_cancel", "arguments": arguments}},
        {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
    )


class TestsCancelToolTests(unittest.TestCase):
    def test_request_id_is_required_before_anything_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(server_batch_orchestrator, "invoke_bridge") as bridge:
                with self.assertRaises(JsonRpcError) as raised:
                    _call({"projectRoot": temp})
        self.assertIn("requestId", str(raised.exception))
        bridge.assert_not_called()

    def test_an_accepted_cancel_journals_a_non_retryable_event_and_waits_for_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Assets").mkdir()
            (root / "ProjectSettings").mkdir()
            payload = {"cancel_accepted": True, "operation": "unity.tests.run_editmode", "request_id": "run-1"}
            bridge_response = {"status": "ok", "payload_json": json.dumps(payload), "request_id": "c-1"}

            def fake_bridge(project_root, operation, args, timeout_ms):
                self.assertEqual("unity.tests.cancel", operation)
                self.assertEqual({"requestId": "run-1"}, args)
                return bridge_response

            def fake_events(project_root, request_id):
                return [{"event_type": "request_completed"}] if request_id == "run-1" else []

            with mock.patch.object(server_batch_orchestrator, "invoke_bridge", side_effect=fake_bridge), mock.patch.object(
                server_batch_orchestrator, "ensure_project_root", return_value=root
            ), mock.patch.object(
                server_batch_orchestrator,
                "read_request_journal_events",
                side_effect=fake_events,
            ), mock.patch.object(
                server_batch_orchestrator,
                "build_request_final_status_from_context",
                return_value={"result_trust_class": "unity_cancelled_confirmed", "request_id": "run-1"},
            ):
                response = _call({"projectRoot": temp, "requestId": "run-1"})

            result = response["result"]
            self.assertFalse(result["isError"])
            content = result["structuredContent"]
            self.assertTrue(content["run_completed_after_cancel"])
            self.assertEqual("unity_cancelled_confirmed", content["request_final_status"]["result_trust_class"])
            events = read_request_journal_events(root, "run-1")
            cancel_events = [event for event in events if event.get("event_type") == "request_cancel_requested"]
            self.assertEqual(1, len(cancel_events))
            self.assertFalse(cancel_events[0]["retryable"])


class CancelledVerdictTests(unittest.TestCase):
    def test_a_cancelled_payload_is_its_own_terminal_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            summary = build_test_verdict_summary(
                project_root=Path(temp),
                request_id="r",
                operation="unity.tests.run_editmode",
                response_payload={
                    "total": 3, "passed": 1, "failed": 0, "skipped": 0, "cancelled": True,
                    "completed_at_utc": "2026-11-06T03:20:00Z", "run_phase": "completed",
                },
                persisted_test_result=None,
                request_submitted=True,
                request_started=True,
                request_completed=True,
                completion_status="ok",
                operation_outcome="completed_ok",
                active_state=None,
                bridge_changed_since_submission=False,
            )
        self.assertEqual("cancelled", summary["test_verdict"])
        self.assertEqual("unity_cancelled_confirmed", summary["result_trust_class"])
        self.assertEqual("none", summary["recommended_next_action"])


if __name__ == "__main__":
    unittest.main()
