import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server
import server_batch_orchestrator
import server_scenario_polling
from server_core import ToolInvocationError


NON_MAIN_DETAILS = {
    "request_submitted": False,
    "transport_outcome": "request_not_submitted",
    "recommended_next_action": "wait_for_main_editor_bridge_then_retry",
}


def _call_run_and_wait(project_root: Path) -> dict:
    return server.handle_json_rpc_message(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "unity_scenario_run_and_wait",
                "arguments": {
                    "projectRoot": str(project_root),
                    "scenario": {"name": "DispatchTruth", "steps": []},
                },
            },
        },
        {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
    )


def _run_response(project_root: Path) -> dict:
    return {
        "status": "ok",
        "payload_type": "unity.scenario.run",
        "payload_json": json.dumps(
            {"project_root": str(project_root), "run_id": "run-15", "scenario_name": "DispatchTruth", "status": "queued"}
        ),
    }


class RunAndWaitDispatchTruthTests(unittest.TestCase):
    def test_poll_refusal_after_dispatch_reports_submitted_run_and_poll_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            with (
                mock.patch.object(server, "ensure_project_root", return_value=project_root),
                mock.patch.object(server, "invoke_bridge", return_value=_run_response(project_root)),
                mock.patch.object(
                    server,
                    "wait_for_scenario_result",
                    side_effect=ToolInvocationError("bridge_owned_by_non_main_process", "worker", dict(NON_MAIN_DETAILS)),
                ),
            ):
                response = _call_run_and_wait(project_root)

        self.assertTrue(response["result"]["isError"])
        error = response["result"]["structuredContent"]["error"]
        details = error.get("details") or response["result"]["structuredContent"]
        flat = json.dumps(response["result"]["structuredContent"])
        self.assertEqual("scenario_wait_failed_after_dispatch", error["code"])
        self.assertIn('"scenario_run_submitted": true', flat)
        self.assertIn('"request_submitted": true', flat)
        self.assertIn('"scenario_wait_error_code": "bridge_owned_by_non_main_process"', flat)
        self.assertIn('"run_id": "run-15"', flat)
        self.assertIn("poll_scenario_result_do_not_rerun", flat)
        self.assertNotIn('"request_submitted": false', flat)
        self.assertIsInstance(details, dict)

    def test_refusal_before_dispatch_stays_not_submitted_and_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            refusal = ToolInvocationError(
                "bridge_owned_by_non_main_process",
                "worker",
                {**NON_MAIN_DETAILS, "retryable": True},
            )
            wait = mock.Mock()
            with (
                mock.patch.object(server, "ensure_project_root", return_value=project_root),
                mock.patch.object(server, "invoke_bridge", side_effect=refusal),
                mock.patch.object(server, "wait_for_scenario_result", wait),
            ):
                response = _call_run_and_wait(project_root)

        wait.assert_not_called()
        flat = json.dumps(response["result"]["structuredContent"])
        self.assertIn('"code": "bridge_owned_by_non_main_process"', flat)
        self.assertIn('"scenario_run_submitted": false', flat)
        self.assertIn('"retryable": true', flat)


class ScenarioPollTransientOwnerTests(unittest.TestCase):
    def _wait(self, project_root: Path, invoke, reconcile) -> dict:
        return server_scenario_polling.wait_for_scenario_result_data(
            project_root,
            "run-15",
            "DispatchTruth",
            3000,
            100,
            scenario_recovery_error_codes=frozenset(),
            scenario_terminal_statuses={"passed", "failed"},
            default_heartbeat_max_age_seconds=10,
            try_read_live_editor_state=lambda _root: None,
            activate_unity_editor=lambda _root: None,
            invoke_bridge=invoke,
            recover_project_bridge_for_reconciliation=lambda *a, **k: {},
            current_project_context_bridge_state=lambda _root: {},
            enrich_tool_invocation_error_with_discovery=lambda _root, exc: exc,
            bridge_response_to_tool_result=lambda response: {"structuredContent": json.loads(response["payload_json"])},
            normalize_scenario_payload=lambda payload, _statuses: payload,
            apply_discovery_to_scenario_payload=lambda payload, _root: payload,
            reconcile_persisted_scenario_result=reconcile,
            tool_invocation_error_type=ToolInvocationError,
        )

    def test_non_main_owner_during_poll_is_transient(self) -> None:
        calls = {"count": 0}

        def invoke(_root, _operation, _args, _timeout):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ToolInvocationError("bridge_owned_by_non_main_process", "worker", dict(NON_MAIN_DETAILS))
            return {"payload_json": json.dumps({"run_id": "run-15", "status": "passed"})}

        with mock.patch.object(server_scenario_polling.time, "sleep"):
            payload = self._wait(Path("/tmp/p"), invoke, lambda *_a: {})

        self.assertEqual("passed", payload["status"])
        self.assertEqual(2, calls["count"])

    def test_non_transient_poll_error_returns_persisted_terminal_result(self) -> None:
        def invoke(_root, _operation, _args, _timeout):
            raise ToolInvocationError("editor_idle_timeout", "busy", {})

        def reconcile(_root, _run_id, _name):
            return {
                "terminal_result_found": True,
                "lookup_found": True,
                "lookup_strategy": "run_id",
                "payload": {"run_id": "run-15", "status": "failed"},
                "matched_result_count": 1,
                "terminal_result_count": 1,
            }

        payload = self._wait(Path("/tmp/p"), invoke, reconcile)
        self.assertEqual("failed", payload["status"])
        self.assertTrue(payload["scenario_result_reconciled_from_persisted"])
        self.assertEqual(
            "terminal_persisted_result_after_poll_error:editor_idle_timeout",
            payload["scenario_result_reconciliation_reason"],
        )


class NonMainOwnerDispatchGateTests(unittest.TestCase):
    def test_owner_that_returns_to_main_editor_is_not_refused(self) -> None:
        cleared = SimpleNamespace(discovery_details={"bridge_owned_by_non_main_process": False})
        with (
            mock.patch.object(server_batch_orchestrator, "refresh_project_context", return_value=cleared),
            mock.patch.object(server_batch_orchestrator, "NON_MAIN_OWNER_POLL_SECONDS", 0.0),
        ):
            discovery, wait = server_batch_orchestrator.await_main_bridge_owner(
                Path("/tmp/p"), {"bridge_owned_by_non_main_process": True, "bridge_pid": 41}, 5000
            )
        self.assertFalse(discovery["bridge_owned_by_non_main_process"])
        self.assertTrue(wait["non_main_owner_cleared"])
        self.assertEqual(41, wait["non_main_owner_pid"])

    def test_owner_that_stays_non_main_is_refused_as_retryable_not_submitted(self) -> None:
        held = SimpleNamespace(discovery_details={"bridge_owned_by_non_main_process": True, "bridge_pid": 41})
        context = SimpleNamespace(project_root=Path("/tmp/p"), discovery_details=dict(held.discovery_details))
        with (
            mock.patch.object(server_batch_orchestrator, "refresh_project_context", return_value=held),
            mock.patch.object(server_batch_orchestrator, "NON_MAIN_OWNER_WAIT_MAX_MS", 30),
            mock.patch.object(server_batch_orchestrator, "NON_MAIN_OWNER_POLL_SECONDS", 0.01),
            mock.patch.object(server_batch_orchestrator, "record_request_refused_event", create=True),
        ):
            with self.assertRaises(ToolInvocationError) as raised:
                server_batch_orchestrator._invoke_bridge_locked(context, "unity.scenario.run", {}, 5000)
        details = raised.exception.details
        self.assertEqual("bridge_owned_by_non_main_process", raised.exception.code)
        self.assertFalse(details["request_submitted"])
        self.assertTrue(details["retryable"])
        self.assertFalse(details["non_main_owner_cleared"])
        self.assertEqual("wait_for_main_editor_bridge_then_retry", details["recommended_next_action"])


if __name__ == "__main__":
    unittest.main()
