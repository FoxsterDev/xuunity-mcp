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
import server_bridge_state as state_owner
import server_health
from server_bridge_paths import scenario_results_dir
from server_core import ToolInvocationError, write_json

BUILDING_STATE = {
    "editor_pid": 321,
    "heartbeat_utc": "2026-11-05T10:00:00Z",
    "busy_reason": "build_player",
    "busy_reason_detail": "target:Android:started:2026-11-05T09:59:58Z",
    "active_operation": "unity.project_action.invoke",
    "health_status": "healthy",
}


class BuildPlayerIdleTimeoutTests(unittest.TestCase):
    def test_stale_heartbeat_during_a_build_is_unresponsive_busy_never_a_recovery(self) -> None:
        with (
            mock.patch.object(state_owner, "pid_is_alive", return_value=True),
            mock.patch.object(state_owner, "heartbeat_age_seconds", return_value=240.0),
        ):
            details = state_owner.build_editor_idle_timeout_details(
                Path("/project"),
                last_state=dict(BUILDING_STATE),
                reason="before unity.scenario.result",
                timeout_ms=5000,
                heartbeat_max_age_seconds=10,
                require_healthy_bridge=True,
            )
        self.assertEqual("editor_alive_but_unresponsive", details["classification"])
        self.assertTrue(details["editor_busy_in_build"])
        self.assertEqual("build_player_in_progress", details["unresponsive_cause"])
        self.assertEqual("wait_for_build_player_to_finish", details["recommended_next_action"])
        self.assertIn("request-status-summary", details["recommended_recovery_command"])
        self.assertNotIn("recover-editor-session", details["recommended_recovery_command"])
        self.assertFalse(details["safe_to_retry"])

    def test_dead_pid_after_a_build_is_still_frozen(self) -> None:
        with (
            mock.patch.object(state_owner, "pid_is_alive", return_value=False),
            mock.patch.object(state_owner, "heartbeat_age_seconds", return_value=240.0),
        ):
            details = state_owner.build_editor_idle_timeout_details(
                Path("/project"),
                last_state=dict(BUILDING_STATE),
                reason="x",
                timeout_ms=5000,
                heartbeat_max_age_seconds=10,
                require_healthy_bridge=True,
            )
        self.assertEqual("editor_state_frozen", details["classification"])
        self.assertFalse(details["editor_busy_in_build"])

    def test_a_build_is_never_idle(self) -> None:
        self.assertFalse(state_owner.state_is_idle({"busy_reason": "build_player"}))
        self.assertIn(
            "build_player_in_progress",
            state_owner.idle_wait_blocking_reasons(
                dict(BUILDING_STATE), heartbeat_max_age_seconds=10, require_healthy_bridge=False
            ),
        )


class BuildPlayerHostHealthTests(unittest.TestCase):
    def test_build_past_the_anr_threshold_is_observe_only(self) -> None:
        health = server_health.classify_project_health(
            bridge_state=dict(BUILDING_STATE),
            discovery={"bridge_state_live": True, "bridge_enabled": True, "bridge_pid_alive": True},
            editor_log_diagnosis={},
            heartbeat_age_seconds=lambda _state: 600.0,
            derive_busy_reason=state_owner.derive_busy_reason,
        )
        self.assertEqual("stale", health["host_health_classification"])
        self.assertEqual("build_player_in_progress", health["host_health_reason"])
        self.assertEqual("observe_only", health["host_health_termination_policy"])
        self.assertEqual("none", health["anr_classification"])

    def test_non_build_stall_keeps_its_anr_classification(self) -> None:
        stalled = dict(BUILDING_STATE, busy_reason="", active_operation="")
        health = server_health.classify_project_health(
            bridge_state=stalled,
            discovery={"bridge_state_live": True, "bridge_enabled": True, "bridge_pid_alive": True},
            editor_log_diagnosis={},
            heartbeat_age_seconds=lambda _state: 600.0,
            derive_busy_reason=state_owner.derive_busy_reason,
        )
        self.assertEqual("anr", health["anr_classification"])


class ScenarioResultPersistedFallbackTests(unittest.TestCase):
    def _call(self, project_root: Path) -> dict:
        return server.handle_json_rpc_message(
            {
                "jsonrpc": "2.0",
                "id": 40,
                "method": "tools/call",
                "params": {"name": "unity_scenario_result", "arguments": {"projectRoot": str(project_root), "runId": "run-40"}},
            },
            {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
        )

    def test_transport_miss_during_a_build_serves_the_persisted_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            results = scenario_results_dir(project_root)
            results.mkdir(parents=True)
            write_json(
                results / "run-40.json",
                {"run_id": "run-40", "scenario_name": "BuildApk", "status": "running", "current_step_index": 2,
                 "updated_at_utc": "2026-11-05T10:00:00Z", "steps": []},
            )
            miss = ToolInvocationError("transport_response_missing", "no response before deadline", {"request_submitted": True})
            with (
                mock.patch.object(server, "ensure_project_root", return_value=project_root),
                mock.patch.object(server_batch_orchestrator, "invoke_bridge", side_effect=miss),
                mock.patch.object(server_batch_orchestrator, "try_read_bridge_state", return_value=dict(BUILDING_STATE)),
            ):
                response = self._call(project_root)

        self.assertFalse(response["result"]["isError"])
        payload = response["result"]["structuredContent"]
        self.assertEqual("persisted_result_file", payload["scenario_result_source"])
        self.assertEqual("transport_response_missing", payload["transport_miss_code"])
        self.assertEqual("running", payload["status"])
        self.assertTrue(payload["editor_busy_in_build"])
        self.assertFalse(payload["persisted_result_terminal"])
        self.assertEqual("wait_for_build_player_to_finish", payload["recommended_next_action"])

    def test_transport_miss_without_a_persisted_result_stays_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            miss = ToolInvocationError("transport_response_missing", "no response", {})
            with (
                mock.patch.object(server, "ensure_project_root", return_value=project_root),
                mock.patch.object(server_batch_orchestrator, "invoke_bridge", side_effect=miss),
            ):
                response = self._call(project_root)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("transport_response_missing", json.dumps(response["result"]["structuredContent"]))


if __name__ == "__main__":
    unittest.main()
