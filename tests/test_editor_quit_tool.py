import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_batch_orchestrator
import server_editor_quit_tool
import server_recovery_commands
import server_specs


def _utc(offset_seconds: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset_seconds))


class EditorQuitBusyGuardTests(unittest.TestCase):
    def test_fresh_playmode_tests_and_operations_are_busy(self) -> None:
        base = {"heartbeat_utc": _utc()}
        self.assertEqual([], server_editor_quit_tool.editor_quit_busy_reasons(base))
        self.assertEqual(["playmode_active"], server_editor_quit_tool.editor_quit_busy_reasons({**base, "is_playing": True}))
        self.assertEqual(
            ["test_run_active"],
            server_editor_quit_tool.editor_quit_busy_reasons({**base, "active_test_run_phase": "running"}),
        )
        self.assertEqual(
            [],
            server_editor_quit_tool.editor_quit_busy_reasons({**base, "active_test_run_phase": "response_written"}),
        )
        self.assertEqual(
            ["operation_active:unity.build.player"],
            server_editor_quit_tool.editor_quit_busy_reasons({**base, "active_operation": "unity.build.player"}),
        )

    def test_stale_or_missing_state_does_not_block(self) -> None:
        stale = {"heartbeat_utc": _utc(-600), "is_playing": True}
        self.assertEqual([], server_editor_quit_tool.editor_quit_busy_reasons(stale))
        self.assertEqual([], server_editor_quit_tool.editor_quit_busy_reasons(None))
        self.assertEqual([], server_editor_quit_tool.editor_quit_busy_reasons({"is_playing": True}))


class EditorQuitToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name).resolve()
        self.quit_response = {
            "status": "ok",
            "request_id": "quit-1",
            "payload_json": json.dumps({"editor_pid": 4242, "quit_mechanism": "update_one_shot"}),
            "_xuunity_lifecycle": {"large": "x" * 4000},
        }
        self.closed = {
            "same_project_editor_closed": True,
            "process_exit_verified": True,
            "process_visibility_available": True,
            "live_project_editor_pids": [],
        }

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _call(self, arguments: dict, *, state=None, verification=None, quit_response=None):
        patches = [
            mock.patch.object(server_editor_quit_tool, "ensure_project_root", return_value=self.root),
            mock.patch.object(server_editor_quit_tool, "try_read_bridge_state", return_value=state),
            mock.patch.object(
                server_editor_quit_tool, "request_editor_quit", return_value=dict(quit_response or self.quit_response)
            ),
            mock.patch.object(
                server_editor_quit_tool, "verify_project_editor_closed", return_value=dict(verification or self.closed)
            ),
            mock.patch.object(server_editor_quit_tool, "read_request_journal_events", return_value=[]),
            mock.patch.object(server_editor_quit_tool, "try_read_host_editor_session_state", return_value={}),
        ]
        with patches[0], patches[1], patches[2] as request_quit, patches[3] as verify, patches[4], patches[5]:
            result = server_batch_orchestrator.call_tool(
                "unity_editor_quit", {"projectRoot": str(self.root), **arguments}
            )
        return result, request_quit, verify

    def test_tool_is_declared_with_required_approval(self) -> None:
        tool = server_specs.TOOLS["unity_editor_quit"]
        self.assertEqual(["projectRoot", "approve"], tool["inputSchema"]["required"])
        self.assertIn("closeout_classification", tool["description"])

    def test_quit_without_approval_is_refused_before_any_request(self) -> None:
        result, request_quit, _ = self._call({"approve": False})
        request_quit.assert_not_called()
        self.assertTrue(result["isError"])
        self.assertIn("editor_quit_approval_required", result["content"][0]["text"])

    def test_busy_editor_is_refused_unless_allowed(self) -> None:
        busy = {"heartbeat_utc": _utc(), "is_playing": True, "active_test_run_phase": "running"}
        result, request_quit, _ = self._call({"approve": True}, state=busy)
        request_quit.assert_not_called()
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("editor_quit_refused_editor_busy", text)
        self.assertIn("playmode_active", text)
        self.assertIn("test_run_active", text)

        allowed, request_quit, _ = self._call({"approve": True, "allowWhileBusy": True}, state=busy)
        request_quit.assert_called_once()
        self.assertFalse(allowed["isError"])

    def test_verified_quit_returns_a_compact_closeout(self) -> None:
        result, request_quit, verify = self._call({"approve": True, "exitTimeoutMs": 45000})
        request_quit.assert_called_once_with(str(self.root), 15000)
        verify.assert_called_once_with(self.root, 45000)
        payload = json.loads(result["content"][0]["text"])
        self.assertFalse(result["isError"])
        self.assertEqual("quit_ack_and_process_exit_verified", payload["closeout_classification"])
        self.assertEqual(4242, payload["editor_pid"])
        self.assertNotIn("quit_request", payload)
        self.assertLess(len(result["content"][0]["text"]), 1500)

        full, _, _ = self._call({"approve": True, "includeFullPayload": True})
        self.assertIn("quit_request", json.loads(full["content"][0]["text"]))

    def test_ack_without_exit_is_an_error_with_the_classification(self) -> None:
        still_running = {
            "same_project_editor_closed": False,
            "process_exit_verified": False,
            "process_visibility_available": True,
            "live_project_editor_pids": [4242],
        }
        result, _, _ = self._call({"approve": True}, verification=still_running)
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("editor_quit_ack_without_exit", text)
        self.assertNotIn("x" * 100, text)

    def test_no_wait_returns_unverified_ack(self) -> None:
        result, _, verify = self._call({"approve": True, "waitForExit": False})
        verify.assert_not_called()
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual("quit_ack_unverified", payload["closeout_classification"])

    def test_rejected_quit_and_bad_arguments(self) -> None:
        rejected = {"status": "error", "error": {"code": "bridge_unavailable", "message": "no editor"}}
        result, _, _ = self._call({"approve": True}, quit_response=rejected)
        self.assertTrue(result["isError"])
        self.assertIn("quit_request_rejected", result["content"][0]["text"])
        with self.assertRaises(server_batch_orchestrator.JsonRpcError):
            self._call({"approve": "yes"})
        with self.assertRaises(server_batch_orchestrator.JsonRpcError):
            self._call({"approve": True, "exitTimeoutMs": 5})


class RecoveryToolHintTests(unittest.TestCase):
    def test_closeout_and_readiness_actions_name_an_mcp_tool(self) -> None:
        self.assertEqual(
            "unity_editor_quit",
            server_recovery_commands.recommended_recovery_tool_for_action(
                "close_same_project_editor_or_use_interactive_lane"
            ),
        )
        self.assertEqual(
            "unity_ensure_ready", server_recovery_commands.recommended_recovery_tool_for_action("open_editor_or_ensure_ready")
        )
        self.assertEqual("", server_recovery_commands.recommended_recovery_tool_for_action("none"))
        for tool in set(server_recovery_commands.RECOVERY_TOOL_BY_NEXT_ACTION.values()):
            self.assertIn(tool, server_specs.TOOLS)
        self.assertEqual({}, server_recovery_commands.with_recovery_tool({}, "inspect_editor_log"))

    def test_batch_editor_conflict_details_name_the_quit_tool(self) -> None:
        details = server_batch_orchestrator.build_batch_editor_conflict_details(Path("/tmp/p"), [4242])
        self.assertEqual("unity_editor_quit", details["recommended_recovery_tool"])


if __name__ == "__main__":
    unittest.main()
