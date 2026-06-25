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
import server_bridge_payloads
import server_summaries


class ScenarioDecisionVerdictTests(unittest.TestCase):
    def _call_run_and_wait(self, project_root: Path, arguments: dict) -> dict:
        return server.handle_json_rpc_message(
            {
                "jsonrpc": "2.0",
                "id": 41,
                "method": "tools/call",
                "params": {
                    "name": "unity_scenario_run_and_wait",
                    "arguments": {
                        "projectRoot": str(project_root),
                        "scenario": {"name": "DecisionSmoke", "steps": []},
                        **arguments,
                    },
                },
            },
            {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
        )

    def test_run_and_wait_defaults_to_compact_decision_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            heavy_payload = "x" * 5000
            run_payload = {
                "project_root": str(project_root),
                "run_id": "run-compact",
                "scenario_name": "DecisionSmoke",
                "status": "queued",
                "editor_relaunched": True,
                "previous_editor_pid": 0,
                "current_editor_pid": 333,
                "bridge_generation_before": 1,
                "bridge_generation_after": 2,
                "cold_start_reason": "host_launchable_not_active",
            }
            result_payload = {
                "project_root": str(project_root),
                "run_id": "run-compact",
                "scenario_name": "DecisionSmoke",
                "status": "passed",
                "terminal": True,
                "succeeded": True,
                "total_steps": 1,
                "passed_steps": 1,
                "failed_steps": 0,
                "skipped_steps": 0,
                "result_path": str(project_root / "Library" / "XUUnityLightMcp" / "scenarios" / "results" / "run-compact.json"),
                "steps": [
                    {
                        "stepId": "assert_ui",
                        "kind": "scene_assert",
                        "status": "passed",
                        "outcome": "assertion_passed",
                        "payload_json": json.dumps({"large": heavy_payload}),
                    }
                ],
            }

            with (
                mock.patch.object(server, "ensure_project_root", return_value=project_root),
                mock.patch.object(
                    server,
                    "invoke_bridge",
                    return_value={
                        "status": "ok",
                        "payload_type": "unity.scenario.run",
                        "payload_json": json.dumps(run_payload),
                    },
                ),
                mock.patch.object(server, "wait_for_scenario_result", return_value=dict(result_payload)),
            ):
                response = self._call_run_and_wait(project_root, {})

        self.assertFalse(response["result"]["isError"])
        structured = response["result"]["structuredContent"]
        self.assertEqual("passed", structured["verdict"])
        self.assertEqual("authoritative", structured["trust_class"])
        self.assertEqual("passed", structured["scenario_status"])
        self.assertTrue(structured["full_payload_available"])
        self.assertEqual("none", structured["recommended_next_action"])
        self.assertTrue(structured["editor_relaunched"])
        self.assertEqual(0, structured["previous_editor_pid"])
        self.assertEqual(333, structured["current_editor_pid"])
        self.assertEqual(1, structured["bridge_generation_before"])
        self.assertEqual(2, structured["bridge_generation_after"])
        self.assertEqual("host_launchable_not_active", structured["cold_start_reason"])
        self.assertEqual(
            [{"step_id": "assert_ui", "kind": "scene_assert", "status": "passed", "outcome": "assertion_passed", "duration_seconds": 0.0}],
            structured["steps"],
        )
        self.assertNotIn("run_start", structured)
        self.assertNotIn(heavy_payload, json.dumps(structured))

    def test_run_and_wait_verbose_preserves_full_payload_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            heavy_payload = "y" * 5000
            result_payload = {
                "project_root": str(project_root),
                "run_id": "run-full",
                "scenario_name": "DecisionSmoke",
                "status": "passed",
                "terminal": True,
                "succeeded": True,
                "steps": [
                    {
                        "stepId": "hook",
                        "kind": "project_defined_hook",
                        "status": "passed",
                        "payload_json": json.dumps({"large": heavy_payload}),
                    }
                ],
            }

            with (
                mock.patch.object(server, "ensure_project_root", return_value=project_root),
                mock.patch.object(
                    server,
                    "invoke_bridge",
                    return_value={
                        "status": "ok",
                        "payload_type": "unity.scenario.run",
                        "payload_json": json.dumps(
                            {
                                "project_root": str(project_root),
                                "run_id": "run-full",
                                "scenario_name": "DecisionSmoke",
                                "status": "queued",
                            }
                        ),
                    },
                ),
                mock.patch.object(server, "wait_for_scenario_result", return_value=dict(result_payload)),
            ):
                response = self._call_run_and_wait(project_root, {"verbose": True})

        self.assertFalse(response["result"]["isError"])
        structured = response["result"]["structuredContent"]
        self.assertEqual("passed", structured["status"])
        self.assertIn("run_start", structured)
        self.assertEqual(json.dumps({"large": heavy_payload}), structured["steps"][0]["payload_json"])

    def test_run_and_wait_failed_default_returns_compact_error_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            heavy_payload = "z" * 5000
            result_payload = {
                "project_root": str(project_root),
                "run_id": "run-failed",
                "scenario_name": "DecisionSmoke",
                "status": "failed",
                "terminal": True,
                "succeeded": False,
                "steps": [
                    {
                        "stepId": "flow",
                        "kind": "project_defined_hook_poll_until",
                        "status": "failed",
                        "outcome": "hook_poll_until_failed",
                        "failure_class": "product_assertion",
                        "error_code": "ui_assertion_failed",
                        "payload_json": json.dumps({"large": heavy_payload}),
                    }
                ],
            }

            with (
                mock.patch.object(server, "ensure_project_root", return_value=project_root),
                mock.patch.object(
                    server,
                    "invoke_bridge",
                    return_value={
                        "status": "ok",
                        "payload_type": "unity.scenario.run",
                        "payload_json": json.dumps(
                            {
                                "project_root": str(project_root),
                                "run_id": "run-failed",
                                "scenario_name": "DecisionSmoke",
                                "status": "queued",
                            }
                        ),
                    },
                ),
                mock.patch.object(server, "wait_for_scenario_result", return_value=dict(result_payload)),
            ):
                response = self._call_run_and_wait(project_root, {})

        self.assertTrue(response["result"]["isError"])
        structured = response["result"]["structuredContent"]
        self.assertEqual("failed", structured["verdict"])
        self.assertEqual("authoritative", structured["trust_class"])
        self.assertEqual("product_assertion", structured["failure_class"])
        self.assertEqual("scenario_failed", structured["error"]["code"])
        self.assertNotIn("scenario", structured)
        self.assertNotIn(heavy_payload, json.dumps(structured))

    def test_scenario_summary_promotes_ui_smoke_fields_and_path_coverage(self) -> None:
        payload = {
            "project_root": "/tmp/FakeProject",
            "run_id": "run-ui",
            "scenario_name": "UiSmoke",
            "status": "passed",
            "steps": [
                {
                    "stepId": "flow",
                    "kind": "project_defined_hook_poll_until",
                    "status": "passed",
                    "outcome": "hook_poll_until_passed",
                    "hook_name": "example.ui_smoke",
                    "payload_json": json.dumps(
                        {
                            "status": "passed",
                            "user_path": "primary_path",
                            "selected_tab": "Rewards",
                            "before_model": {"coins": 10},
                            "after_model": {"coins": 20},
                            "before_ui": "10",
                            "after_ui": "20",
                            "blocking_popup": "",
                            "failure_class": "",
                            "screenshot_path": "/tmp/ui.png",
                            "required_path_rows": [
                                {"path": "primary_path", "label": "Primary"},
                                {"path": "hidden_tab_update", "label": "Hidden Tab"},
                            ],
                        }
                    ),
                }
            ],
        }

        summary = server_summaries.build_scenario_result_summary(payload, {"passed", "failed"})

        ui = summary["ui_smoke_summary"]
        self.assertEqual("primary_path", ui["user_path"])
        self.assertEqual("Rewards", ui["selected_tab"])
        self.assertEqual({"coins": 20}, ui["after_model"])
        self.assertEqual("/tmp/ui.png", ui["screenshot_path"])

        coverage = summary["path_coverage_summary"]
        self.assertEqual("primary_path", coverage["reported_path"])
        self.assertEqual(2, coverage["required_path_count"])
        self.assertEqual("passed", coverage["rows"][0]["status"])
        self.assertEqual("unavailable", coverage["rows"][1]["status"])
        self.assertFalse(coverage["all_required_paths_passed"])

    def test_decision_verdict_classifies_project_refresh_timeout_as_infrastructure(self) -> None:
        payload = {
            "project_root": "/tmp/FakeProject",
            "run_id": "run-infra",
            "scenario_name": "RefreshThenCompile",
            "status": "failed",
            "terminal": True,
            "succeeded": False,
            "steps": [
                {
                    "stepId": "refresh",
                    "kind": "project_refresh",
                    "status": "failed",
                    "outcome": "refresh_timeout",
                    "error_code": "project_refresh_timeout",
                    "error_message": "Timed out waiting for refresh settle.",
                },
                {
                    "stepId": "compile",
                    "kind": "compile_player_scripts",
                    "status": "passed",
                    "outcome": "compile_passed",
                    "payload_json": json.dumps({"post_settle_compile": "passed", "post_settle_error_count": 0}),
                },
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        self.assertEqual("inconclusive", verdict["verdict"])
        self.assertEqual("infrastructure_timeout", verdict["trust_class"])
        self.assertEqual("infrastructure_timeout", verdict["failure_class"])
        self.assertEqual("failed", verdict["scenario_status"])
        self.assertEqual("refresh", verdict["first_failure"]["step_id"])
        self.assertEqual("failed", verdict["steps"][0]["status"])

    def test_refresh_payload_exposes_authoritative_post_settle_compile_truth(self) -> None:
        normalized = server_bridge_payloads.normalize_refresh_payload_from_lifecycle(
            {
                "outcome": "refresh_requested",
                "package_resolve_requested": False,
                "settle_request_id": "req-refresh",
                "compiler_error_count": 2,
                "recent_compiler_diagnostics": [{"message": "stale error"}],
            },
            {
                "idle_wait_after": {
                    "heartbeat_utc": "2026-06-25T10:00:00Z",
                    "refresh_settle_phase": "settled",
                    "refresh_settle_request_id": "req-refresh",
                    "refresh_settle_completed_utc": "2026-06-25T10:00:01Z",
                    "is_compiling": False,
                    "is_updating": False,
                    "playmode_state": "edit",
                    "script_compilation_failed": False,
                    "compiler_error_count": 0,
                    "recent_compiler_diagnostics": [],
                    "compiler_diagnostics_source": "compilation_pipeline",
                }
            },
        )

        self.assertEqual("idle_wait_after", normalized["authoritative_state_source"])
        self.assertEqual("passed", normalized["post_settle_compile"])
        self.assertEqual(0, normalized["post_settle_error_count"])
        self.assertEqual([], normalized["post_settle_diagnostics"])
        self.assertEqual(0, normalized["compiler_error_count"])
        self.assertEqual([], normalized["recent_compiler_diagnostics"])
        self.assertEqual("settled", normalized["settle_phase"])
        self.assertEqual("unity_refresh_settle_watcher", normalized["completion_basis"])

    def test_response_payload_promotes_editor_relaunch_attribution_from_lifecycle(self) -> None:
        response = server_bridge_payloads.normalize_response_payload_from_lifecycle(
            {
                "status": "ok",
                "payload_type": "unity.project.refresh",
                "payload_json": json.dumps(
                    {
                        "outcome": "refresh_requested",
                        "package_resolve_requested": False,
                        "settle_request_id": "req-refresh",
                    }
                ),
            },
            {
                "operation": "unity.project.refresh",
                "activation": {
                    "action": "opened_editor",
                    "editor_relaunched": True,
                    "previous_editor_pid": 0,
                    "current_editor_pid": 456,
                    "bridge_generation_before": 7,
                    "bridge_generation_after": 8,
                    "cold_start_reason": "host_launchable_not_active",
                },
                "idle_wait_after": {
                    "heartbeat_utc": "2026-06-25T10:00:00Z",
                    "refresh_settle_phase": "settled",
                    "refresh_settle_request_id": "req-refresh",
                    "refresh_settle_completed_utc": "2026-06-25T10:00:01Z",
                    "is_compiling": False,
                    "is_updating": False,
                    "playmode_state": "edit",
                    "script_compilation_failed": False,
                    "compiler_error_count": 0,
                    "recent_compiler_diagnostics": [],
                },
            },
            normalize_scenario_payload=server_summaries.normalize_scenario_payload,
            scenario_terminal_statuses={"passed", "failed"},
        )

        payload = json.loads(response["payload_json"])
        self.assertTrue(payload["editor_relaunched"])
        self.assertEqual(0, payload["previous_editor_pid"])
        self.assertEqual(456, payload["current_editor_pid"])
        self.assertEqual(7, payload["bridge_generation_before"])
        self.assertEqual(8, payload["bridge_generation_after"])
        self.assertEqual("host_launchable_not_active", payload["cold_start_reason"])


if __name__ == "__main__":
    unittest.main()
