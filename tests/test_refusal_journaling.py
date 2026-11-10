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

import server_batch_orchestrator as orchestrator
import server_bridge_journal as journal
from server_bridge_paths import request_journal_dir
from server_core import ToolInvocationError, read_json

POLICY = {
    "activate_unity": False,
    "wait_for_idle_before": True,
    "wait_for_idle_after": False,
    "idle_stable_cycles_after": 1,
    "retry_on_lifecycle_reset": False,
    "retry_on_transport_response_missing": False,
    "retry_on_transport_connect_failed": False,
    "post_reset_recovery_cap_ms": 0,
}


def _refusals(root: Path) -> list[dict]:
    return [read_json(path) for path in request_journal_dir(root).glob("*request_refused.json")]


class RefusalJournalingTests(unittest.TestCase):
    def _invoke(self, root: Path, operation: str, **patches):
        context = SimpleNamespace(project_root=root, discovery_details=patches.pop("discovery", {}))
        defaults = {
            "get_project_context": mock.Mock(return_value=context),
            "run_in_project_request_lock": mock.Mock(side_effect=lambda _c, _o, cb: cb()),
            "resolve_operation_lifecycle_policy": mock.Mock(return_value=dict(POLICY)),
            "try_read_live_editor_state": mock.Mock(return_value={"bridge_generation": 3}),
            "current_project_context_bridge_state": mock.Mock(return_value={"bridge_generation": 3}),
            "fail_if_compile_broken_for_operation": mock.Mock(return_value=False),
            "wait_for_editor_idle": mock.Mock(return_value={}),
            "enrich_tool_invocation_error_with_discovery": mock.Mock(side_effect=lambda _root, exc: exc),
            "refresh_project_context": mock.Mock(),
        }
        defaults.update(patches)
        with mock.patch.multiple(orchestrator, **defaults):
            try:
                return orchestrator.invoke_bridge(str(root), operation, {}, 1000)
            except ToolInvocationError as exc:
                return exc

    def test_a_path_in_refusal_details_is_stringified_not_a_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            refusal = ToolInvocationError("editor_idle_timeout", "busy", {"editor_log_path": root / "Editor.log"})
            result = self._invoke(root, "unity.tests.run_editmode", wait_for_editor_idle=mock.Mock(side_effect=refusal))
            self.assertEqual("editor_idle_timeout", result.code)
            events = _refusals(root)
            self.assertEqual(1, len(events))
            self.assertEqual(str(root / "Editor.log"), events[0]["details"]["editor_log_path"])
            self.assertNotIn("refusal_journal_error", result.details)

    def test_transport_stage_refusals_are_journaled_once_under_the_progress_request_id(self) -> None:
        for code in ("bridge_disabled", "editor_not_running", "transport_connect_failed"):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                refusal = ToolInvocationError(
                    code, code, {"request_submitted": False, "transport_outcome": "request_not_submitted"}
                )
                result = self._invoke(root, "unity.status", invoke_bridge_transport=mock.Mock(side_effect=refusal))
                self.assertEqual(code, result.code)
                events = _refusals(root)
                self.assertEqual(1, len(events))
                progress = [
                    read_json(path)
                    for path in request_journal_dir(root).glob("*operation_progress.json")
                ]
                self.assertTrue(progress)
                self.assertEqual({events[0]["request_id"]}, {event["request_id"] for event in progress})

    def test_a_retried_connect_failure_is_not_journaled_as_a_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            refusal = ToolInvocationError("transport_connect_failed", "x", {"request_submitted": False})
            transport = mock.Mock(side_effect=[refusal, ({"status": "ok", "payload_json": ""}, "r2", time.time(), {})])
            policy = dict(POLICY, retry_on_transport_connect_failed=True)
            self._invoke(
                root,
                "unity.status",
                invoke_bridge_transport=transport,
                resolve_operation_lifecycle_policy=mock.Mock(return_value=policy),
                recover_project_bridge_for_reconciliation=mock.Mock(return_value={}),
            )
            self.assertEqual([], _refusals(root))

    def test_a_submitted_request_that_fails_is_not_a_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failure = ToolInvocationError("transport_response_missing", "x", {"request_submitted": True})
            self._invoke(root, "unity.status", invoke_bridge_transport=mock.Mock(side_effect=failure))
            self.assertEqual([], _refusals(root))

    def test_non_main_owner_refusal_is_journaled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch.object(orchestrator, "NON_MAIN_OWNER_WAIT_MAX_MS", 0),
                mock.patch.object(
                    orchestrator,
                    "refresh_project_context",
                    return_value=SimpleNamespace(discovery_details={"bridge_owned_by_non_main_process": True}),
                ),
            ):
                result = self._invoke(
                    root,
                    "unity.scenario.run",
                    discovery={"bridge_owned_by_non_main_process": True, "bridge_pid": 9},
                )
            self.assertEqual("bridge_owned_by_non_main_process", result.code)
            self.assertEqual(1, len(_refusals(root)))

    def test_refused_recovery_refresh_yields_one_event_for_the_operators_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            busy = ToolInvocationError("editor_idle_timeout", "busy before refresh", {"recommended_next_action": "x"})
            result = self._invoke(
                root,
                "unity.tests.run_editmode",
                fail_if_compile_broken_for_operation=mock.Mock(
                    side_effect=lambda _root, operation, _state, _args=None: operation != "unity.project.refresh"
                ),
                wait_for_editor_idle=mock.Mock(side_effect=busy),
            )
            self.assertEqual("editor_idle_timeout", result.code)
            events = _refusals(root)
            self.assertEqual(1, len(events))
            self.assertEqual("unity.tests.run_editmode", events[0]["operation"])
            self.assertEqual("editor_idle_timeout", events[0]["details"]["recovery_refresh_refusal"]["code"])


class DecisionSnapshotTests(unittest.TestCase):
    def test_idle_timeout_fingerprint_is_the_decision_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            error = ToolInvocationError(
                "editor_idle_timeout",
                "busy",
                {"decision_state": {"bridge_generation": 4, "bridge_session_id": "B", "busy_reason": "domain_reload"}},
            )
            path = journal.record_request_refused_event(
                root, "unity.tests.run_editmode", error, {"bridge_generation": 3, "bridge_session_id": "A"}
            )
            event = read_json(path)
        self.assertEqual(4, event["state_fingerprint"]["bridge_generation"])
        self.assertEqual("idle_timeout_snapshot", event["state_fingerprint_source"])

    def test_compile_refusal_fingerprint_is_the_gate_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event = read_json(
                journal.record_request_refused_event(
                    Path(tmp), "unity.tests.run_editmode", ToolInvocationError("compile_broken", "red", {}), {"bridge_generation": 3}
                )
            )
        self.assertEqual("compile_gate", event["state_fingerprint_source"])
        self.assertEqual(3, event["state_fingerprint"]["bridge_generation"])


if __name__ == "__main__":
    unittest.main()


class CapabilityGenerationTests(unittest.TestCase):
    def test_report_from_an_older_domain_is_flagged(self) -> None:
        import server_capability_generation as generation

        behind = generation.capability_report_generation_view({"probe_bridge_generation": 2}, {"bridge_generation": 3})
        current = generation.capability_report_generation_view({"probe_bridge_generation": 3}, {"bridge_generation": 3})
        legacy = generation.capability_report_generation_view({"status": "healthy"}, {"bridge_generation": 3})
        self.assertTrue(behind["capability_report_generation_behind"])
        self.assertEqual(2, behind["capability_report_probe_bridge_generation"])
        self.assertFalse(current["capability_report_generation_behind"])
        self.assertEqual({}, legacy)

    def test_capabilities_tool_reports_the_comparison(self) -> None:
        import json
        import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            response = {
                "status": "ok",
                "payload_type": "unity.capabilities.get",
                "payload_json": json.dumps({"report": {"probe_bridge_generation": 4, "status": "healthy"}}),
            }
            with (
                mock.patch.object(server, "ensure_project_root", return_value=root),
                mock.patch.object(orchestrator, "invoke_bridge", return_value=response),
                mock.patch.object(orchestrator, "try_read_live_editor_state", return_value={"bridge_generation": 5}),
            ):
                result = server.handle_json_rpc_message(
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "unity_capabilities", "arguments": {"projectRoot": str(root)}}},
                    {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
                )
        structured = result["result"]["structuredContent"]
        self.assertTrue(structured["capability_report_generation_behind"])
        self.assertEqual(5, structured["capability_report_current_bridge_generation"])
