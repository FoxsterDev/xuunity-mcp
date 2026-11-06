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
    def test_refresh_timeout_before_mutation_reports_action_not_executed(self) -> None:
        payload = {"status": "failed", "current_step_index": 0, "steps": [
            {"stepId": "refresh", "kind": "project_refresh", "status": "failed",
             "error_code": "project_refresh_timeout", "duration_seconds": 42,
             "timing_measured": True, "execution_duration_seconds": 2, "settle_wait_duration_seconds": 40},
            {"stepId": "change_environment", "kind": "project_defined_hook", "status": "pending"},
        ]}
        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})
        self.assertFalse(verdict["succeeded"])
        boundary = verdict["mutation_boundary"]
        self.assertIsNone(boundary["last_applied_mutation"])
        self.assertEqual("not_executed", boundary["pending_project_actions"][0]["execution_status"])
        self.assertEqual("change_environment", boundary["pending_project_actions"][0]["step_id"])
        self.assertEqual(40, verdict["steps"][0]["settle_wait_duration_seconds"])
        self.assertFalse(boundary["automatic_replay_safe"])
        summary = server_summaries.build_scenario_result_summary(payload, {"passed", "failed"})
        self.assertEqual("refresh", summary["active_step"]["step_id"])

    def test_refresh_timeout_after_mutation_preserves_applied_unsettled_boundary(self) -> None:
        payload = {"status": "failed", "steps": [
            {"stepId": "change_environment", "kind": "project_defined_hook", "status": "passed",
             "payload_json": json.dumps({"outcome": "environment_applied"})},
            {"stepId": "refresh", "kind": "project_refresh", "status": "failed", "error_code": "project_refresh_timeout"},
        ]}
        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})
        self.assertFalse(verdict["succeeded"])
        self.assertEqual("mutation_applied_unsettled", verdict["trust_class"])
        self.assertEqual("change_environment", verdict["mutation_boundary"]["last_applied_mutation"]["step_id"])
        self.assertEqual("unproven", verdict["applied_mutation_settle_summary"]["settle_completion"])
        self.assertNotIn("settle_wait_duration_seconds", verdict["steps"][1])

    def test_refresh_with_unmeasured_timing_does_not_publish_stale_elapsed(self) -> None:
        for measured in (False, None):
            with self.subTest(measured=measured):
                step = {"stepId": "refresh", "kind": "project_refresh", "status": "failed",
                        "duration_seconds": 3, "settle_wait_duration_seconds": 2.75}
                if measured is not None:
                    step["timing_measured"] = measured
                payload = {"status": "failed", "current_step_index": 0, "steps": [step]}
                verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})
                summary = verdict["steps"][0]
                self.assertIsNone(summary["duration_seconds"])
                self.assertIs(summary["timing_measured"], False)
                self.assertNotIn("settle_wait_duration_seconds", summary)

    def test_current_step_zero_is_preserved_and_missing_index_remains_unknown(self) -> None:
        for index, expected in [(0, 0), (None, -1), ("", -1)]:
            with self.subTest(index=index):
                payload = {"status": "running", "current_step_index": index, "steps": []}
                summary = server_summaries.build_scenario_result_summary(payload, {"passed", "failed"})
                self.assertEqual(summary["current_step_index"], expected)

    def test_throttled_step_downgrades_scenario_trust_and_names_remedy(self) -> None:
        payload = {
            "project_root": "/tmp/FakeProject",
            "run_id": "run-throttled",
            "scenario_name": "throttled",
            "status": "passed",
            "steps": [
                {
                    "stepId": "capture",
                    "kind": "game_view_screenshot",
                    "status": "passed",
                    "playmode_state": "playing",
                    "playmode_loop_liveness": "throttled",
                    "editor_application_focused": False,
                    "playmode_liveness_warning": "playmode_throttled_editor_unfocused",
                    "playmode_liveness_remediation": "focus_the_unity_editor_or_set_interaction_mode_to_no_throttling",
                    "result_trust_class": "playmode_throttled",
                }
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        self.assertEqual("passed", verdict["verdict"])
        self.assertEqual("playmode_throttled", verdict["trust_class"])
        self.assertEqual(
            "focus_the_unity_editor_or_set_interaction_mode_to_no_throttling",
            verdict["recommended_next_action"],
        )
        self.assertEqual(["capture"], verdict["playmode_liveness_summary"]["throttled_step_ids"])

    def test_unproven_playing_step_downgrades_scenario_trust(self) -> None:
        payload = {
            "project_root": "/tmp/FakeProject",
            "run_id": "run-unproven",
            "scenario_name": "unproven",
            "status": "passed",
            "steps": [
                {
                    "stepId": "query",
                    "kind": "ui_exists",
                    "status": "passed",
                    "playmode_state": "playing",
                    "playmode_loop_liveness": "unknown",
                    "editor_application_focused": True,
                    "result_trust_class": "playmode_liveness_unproven",
                }
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        self.assertEqual("passed", verdict["verdict"])
        self.assertEqual("playmode_liveness_unproven", verdict["trust_class"])
        self.assertEqual("wait_for_playmode_liveness_sample_and_retry", verdict["recommended_next_action"])
        self.assertEqual(["query"], verdict["playmode_liveness_summary"]["unproven_step_ids"])

    def test_unproven_playmode_control_step_does_not_poison_runtime_evidence_trust(self) -> None:
        payload = {
            "project_root": "/tmp/FakeProject",
            "run_id": "run-control-transition",
            "scenario_name": "control-transition",
            "status": "passed",
            "steps": [
                {
                    "stepId": "wait-play",
                    "kind": "wait_for_playmode_state",
                    "status": "passed",
                    "playmode_state": "playing",
                    "playmode_loop_liveness": "unknown",
                    "editor_application_focused": True,
                    "result_trust_class": "playmode_liveness_unproven",
                }
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        self.assertEqual("passed", verdict["verdict"])
        self.assertEqual("authoritative", verdict["trust_class"])
        self.assertFalse(verdict["playmode_liveness_summary"]["unproven"])
        self.assertEqual([], verdict["playmode_liveness_summary"]["unproven_step_ids"])

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
        self.assertEqual("compact_decision", structured["payload_mode"])
        self.assertEqual("passed", structured["verdict"])
        self.assertEqual("authoritative", structured["trust_class"])
        self.assertEqual("passed", structured["scenario_status"])
        self.assertTrue(structured["full_payload_available"])
        self.assertEqual("compact_summary", structured["steps_payload_mode"])
        self.assertTrue(structured["steps_are_compact"])
        self.assertFalse(structured["raw_steps_included"])
        self.assertTrue(structured["raw_steps_available"])
        self.assertEqual(1, structured["raw_step_count"])
        self.assertEqual(1, structured["compact_step_count"])
        self.assertEqual(
            [
                "request-scenario-result",
                "--project-root",
                str(project_root),
                "--run-id",
                "run-compact",
            ],
            structured["full_payload_cli_args"],
        )
        self.assertEqual("unity_scenario_result", structured["full_payload_tool"])
        self.assertEqual(
            {"projectRoot": str(project_root), "runId": "run-compact"},
            structured["full_payload_tool_arguments"],
        )
        self.assertIn("per_step_payload_json", structured["full_payload_required_for"])
        self.assertIn("hook_name_assertions", structured["full_payload_required_for"])
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
            run_payload = {
                "project_root": str(project_root),
                "run_id": "run-full",
                "scenario_name": "DecisionSmoke",
                "status": "queued",
                "steps": [
                    {
                        "stepId": "hook",
                        "kind": "project_defined_hook",
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
                response = self._call_run_and_wait(project_root, {"verbose": True})

        self.assertFalse(response["result"]["isError"])
        structured = response["result"]["structuredContent"]
        self.assertEqual("passed", structured["status"])
        self.assertIn("run_start", structured)
        self.assertNotIn("steps", structured["run_start"])
        self.assertTrue(structured["run_start"]["steps_omitted"])
        self.assertEqual("omitted_duplicate_run_start_steps", structured["run_start"]["steps_payload_mode"])
        self.assertEqual(json.dumps({"large": heavy_payload}), structured["steps"][0]["payload_json"])

    def test_run_and_wait_include_step_payloads_preserves_run_start_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            run_payload = {
                "project_root": str(project_root),
                "run_id": "run-step-opt-in",
                "scenario_name": "DecisionSmoke",
                "status": "queued",
                "steps": [
                    {
                        "stepId": "launch_step",
                        "kind": "project_defined_hook",
                        "payload_json": json.dumps({"phase": "launch"}),
                    }
                ],
            }
            result_payload = {
                "project_root": str(project_root),
                "run_id": "run-step-opt-in",
                "scenario_name": "DecisionSmoke",
                "status": "passed",
                "terminal": True,
                "succeeded": True,
                "steps": [
                    {
                        "stepId": "terminal_step",
                        "kind": "project_defined_hook",
                        "status": "passed",
                        "payload_json": json.dumps({"phase": "terminal"}),
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
                response = self._call_run_and_wait(
                    project_root,
                    {"includeFullPayload": True, "includeStepPayloads": True},
                )

        self.assertFalse(response["result"]["isError"])
        structured = response["result"]["structuredContent"]
        self.assertEqual("launch_step", structured["run_start"]["steps"][0]["stepId"])
        self.assertEqual("terminal_step", structured["steps"][0]["stepId"])

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
        self.assertEqual("compact_decision", structured["payload_mode"])
        self.assertEqual("failed", structured["verdict"])
        self.assertEqual("authoritative", structured["trust_class"])
        self.assertEqual("product_assertion", structured["failure_class"])
        self.assertEqual("compact_summary", structured["steps_payload_mode"])
        self.assertFalse(structured["raw_steps_included"])
        self.assertTrue(structured["raw_steps_available"])
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

    def test_decision_verdict_separates_applied_hook_mutation_from_refresh_settle_timeout(self) -> None:
        payload = {
            "project_root": "/tmp/FakeProject",
            "run_id": "run-applied-mutation-settle-timeout",
            "scenario_name": "ApplyProfileThenRefresh",
            "status": "failed",
            "terminal": True,
            "succeeded": False,
            "steps": [
                {
                    "stepId": "set_profile",
                    "kind": "project_defined_hook",
                    "status": "passed",
                    "outcome": "operation_succeeded",
                    "payload_json": json.dumps({"outcome": "environment_applied", "environment": "development"}),
                },
                {
                    "stepId": "settle_profile_change",
                    "kind": "project_refresh",
                    "status": "failed",
                    "outcome": "refresh_timeout",
                    "error_code": "project_refresh_timeout",
                    "error_message": "Timed out waiting for refresh settle.",
                },
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        self.assertEqual("inconclusive", verdict["verdict"])
        self.assertEqual("applied_mutation_settle_timeout", verdict["failure_class"])
        self.assertEqual("mutation_applied_unsettled", verdict["trust_class"])
        self.assertEqual("failed", verdict["scenario_status"])
        self.assertEqual("verify_editor_settled_before_next_mutation", verdict["recommended_next_action"])
        self.assertEqual("applied", verdict["applied_mutation_settle_summary"]["mutation_status"])
        self.assertEqual("environment_applied", verdict["applied_mutation_settle_summary"]["mutation_outcome"])
        self.assertEqual("timed_out", verdict["applied_mutation_settle_summary"]["settle_status"])
        self.assertEqual("set_profile", verdict["first_failure"]["mutation_step_id"])
        self.assertTrue(verdict["first_failure"]["settle_timeout_after_applied_mutation"])

    def test_decision_verdict_does_not_overclassify_unproven_mutations(self) -> None:
        base_payload = {
            "project_root": "/tmp/FakeProject",
            "run_id": "run-no-applied-mutation-settle-timeout",
            "scenario_name": "ApplyProfileThenRefresh",
            "status": "failed",
            "terminal": True,
            "succeeded": False,
        }
        applied_hook = {
            "stepId": "set_profile",
            "kind": "project_defined_hook",
            "status": "passed",
            "payload_json": json.dumps({"outcome": "environment_applied"}),
        }
        refresh_timeout = {
            "stepId": "settle_profile_change",
            "kind": "project_refresh",
            "status": "failed",
            "error_code": "project_refresh_timeout",
        }

        for steps in (
            [
                {
                    **applied_hook,
                    "payload_json": json.dumps({"outcome": "environment_requested"}),
                },
                refresh_timeout,
            ],
        ):
            verdict = server_summaries.build_scenario_decision_verdict(
                {**base_payload, "steps": steps},
                {"passed", "failed"},
            )

            self.assertEqual("infrastructure_timeout", verdict["failure_class"])
            self.assertEqual("infrastructure_timeout", verdict["trust_class"])
            self.assertNotIn("applied_mutation_settle_summary", verdict)
            self.assertNotIn("settle_timeout_after_applied_mutation", verdict["first_failure"])

    def test_playmode_set_already_playing_is_compact_stale_state_signal(self) -> None:
        payload = {
            "project_root": "/tmp/FakeProject",
            "run_id": "run-playmode-stale",
            "scenario_name": "EnterPlayMode",
            "status": "passed",
            "terminal": True,
            "succeeded": True,
            "steps": [
                {
                    "stepId": "enter",
                    "kind": "playmode_set",
                    "status": "passed",
                    "outcome": "operation_succeeded",
                    "payload_json": json.dumps(
                        {
                            "requested_action": "enter",
                            "outcome": "already_playing",
                            "settle_phase": "settled",
                            "settle_target_state": "playing",
                            "playmode_state": "playing",
                        }
                    ),
                }
            ],
        }

        summary = server_summaries.build_scenario_result_summary(payload, {"passed", "failed"})

        step = summary["steps"][0]
        self.assertEqual("already_playing", step["outcome"])
        self.assertEqual("operation_succeeded", step["nested_operation_outcome"])
        self.assertTrue(step["stale_playmode_state_detected"])
        self.assertEqual(
            "exit_playmode_then_rerun_if_fresh_start_required",
            step["recommended_next_action"],
        )
        self.assertTrue(summary["playmode_guard_summary"]["stale_playmode_state_detected"])
        self.assertFalse(summary["playmode_guard_summary"]["fresh_playmode_entry_proven"])

    def test_decision_verdict_marks_passed_already_playing_as_stale_risk(self) -> None:
        payload = {
            "project_root": "/tmp/FakeProject",
            "run_id": "run-playmode-risk",
            "scenario_name": "EnterAndAssert",
            "status": "passed",
            "terminal": True,
            "succeeded": True,
            "steps": [
                {
                    "stepId": "enter",
                    "kind": "playmode_set",
                    "status": "passed",
                    "outcome": "already_playing",
                    "payload_json": json.dumps(
                        {
                            "requested_action": "enter",
                            "outcome": "already_playing",
                            "playmode_state": "playing",
                        }
                    ),
                },
                {
                    "stepId": "assert_scene",
                    "kind": "scene_assert",
                    "status": "passed",
                    "outcome": "scene_asserted",
                },
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        self.assertEqual("passed", verdict["verdict"])
        self.assertEqual("stale_risk", verdict["trust_class"])
        self.assertEqual("none", verdict["failure_class"])
        self.assertTrue(verdict["playmode_guard_summary"]["stale_playmode_state_detected"])
        self.assertEqual(
            "exit_playmode_then_rerun_if_fresh_start_required",
            verdict["recommended_next_action"],
        )

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
        self.assertEqual("edit", normalized["playmode_state_after_settle"])
        self.assertEqual("idle_wait_after", normalized["playmode_state_after_settle_source"])
        self.assertEqual("confirmed", normalized["playmode_state_after_settle_trust_class"])

    def test_refresh_never_reports_passed_while_changed_inputs_could_not_be_compiled(self) -> None:
        idle = {
            "heartbeat_utc": "2026-11-05T20:09:00Z",
            "refresh_settle_phase": "settled",
            "refresh_settle_request_id": "req-refresh",
            "refresh_settle_completed_utc": "2026-11-05T20:09:01Z",
            "is_compiling": False,
            "is_updating": False,
            "playmode_state": "edit",
            "script_compilation_failed": False,
            "compiler_error_count": 0,
        }
        base = {"outcome": "refresh_requested", "settle_request_id": "req-refresh"}

        uncompiled = server_bridge_payloads.normalize_refresh_payload_from_lifecycle(
            {**base, "changed_editor_input_count": 1, "changed_editor_inputs": ["Packages/a/A.cs"],
             "script_compilation_requested": False},
            {"idle_wait_after": dict(idle)},
        )
        compile_requested = server_bridge_payloads.normalize_refresh_payload_from_lifecycle(
            {**base, "changed_editor_input_count": 1, "script_compilation_requested": True},
            {"idle_wait_after": dict(idle)},
        )

        self.assertEqual("inconclusive", uncompiled["post_settle_compile"])
        self.assertEqual("editor_domain_stale", uncompiled["post_settle_compile_trust_class"])
        self.assertEqual(
            "rerun_unity_project_refresh_to_compile",
            uncompiled["post_settle_compile_recommended_next_action"],
        )
        self.assertEqual("passed", compile_requested["post_settle_compile"])
        self.assertEqual("confirmed", compile_requested["post_settle_compile_trust_class"])

        unity_already_compiling = server_bridge_payloads.normalize_refresh_payload_from_lifecycle(
            {**base, "changed_editor_input_count": 1, "script_compilation_requested": False,
             "editor_is_compiling_after_request": True},
            {"idle_wait_after": dict(idle)},
        )
        self.assertEqual("passed", unity_already_compiling["post_settle_compile"])

    def test_refresh_playmode_state_is_qualified_after_lifecycle_reset(self) -> None:
        normalized = server_bridge_payloads.normalize_refresh_payload_from_lifecycle(
            {
                "outcome": "refresh_requested",
                "package_resolve_requested": False,
                "settle_request_id": "req-refresh",
            },
            {
                "bridge_identity_transition": {
                    "reclassified_status": "settled_after_lifecycle_reset",
                    "previous_bridge_generation": 4,
                    "current_bridge_generation": 6,
                },
                "idle_wait_after": {
                    "heartbeat_utc": "2026-07-07T10:00:00Z",
                    "refresh_settle_phase": "settled",
                    "refresh_settle_request_id": "req-refresh",
                    "playmode_state": "playing",
                    "is_compiling": False,
                    "is_updating": False,
                    "compiler_error_count": 0,
                },
            },
        )

        self.assertEqual("playing", normalized["playmode_state_after_settle"])
        self.assertEqual("idle_wait_after", normalized["playmode_state_after_settle_source"])
        self.assertEqual("stale_risk", normalized["playmode_state_after_settle_trust_class"])
        self.assertEqual(
            "confirm_via_unity_playmode_state",
            normalized["playmode_state_after_settle_recommended_next_action"],
        )
        self.assertIn("bridge identity changed", normalized["playmode_state_after_settle_note"])

        compact = server_bridge_payloads.compact_operation_payload(normalized, "unity.project.refresh")
        self.assertEqual("playing", compact["playmode_state_after_settle"])
        self.assertEqual("stale_risk", compact["playmode_state_after_settle_trust_class"])
        self.assertEqual(
            "confirm_via_unity_playmode_state",
            compact["playmode_state_after_settle_recommended_next_action"],
        )

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


class RefreshTimeoutRecoveryTests(unittest.TestCase):
    def _refresh_timeout_payload(
        self,
        *,
        step_payload: dict | None = None,
        extra_payload_fields: dict | None = None,
    ) -> dict:
        step = {
            "stepId": "refresh",
            "kind": "project_refresh",
            "status": "failed",
            "outcome": "refresh_waiting_for_settle",
            "error_code": "project_refresh_timeout",
            "error_message": "Timed out waiting for project refresh to settle.",
        }
        if step_payload is not None:
            step["payload_json"] = json.dumps(step_payload)
        payload = {
            "project_root": "/tmp/FakeProject",
            "run_id": "run-refresh-timeout",
            "scenario_name": "RefreshOnly",
            "status": "failed",
            "terminal": True,
            "succeeded": False,
            "steps": [step],
        }
        if extra_payload_fields:
            payload.update(extra_payload_fields)
        return payload

    def _unity_evidence(self, classification: str, **overrides) -> dict:
        evidence = {
            "settle_timed_out": True,
            "settle_timeout_classification": classification,
            "settle_phase_at_timeout": "waiting_for_package_settle",
            "refresh_settle_pending_at_timeout": True,
            "editor_is_compiling_at_timeout": False,
            "editor_is_updating_at_timeout": False,
            "playmode_state_at_timeout": "edit",
            "stable_idle_ticks_at_timeout": 0,
            "operation_may_have_completed": False,
        }
        evidence.update(overrides)
        return evidence

    def test_package_settle_evidence_classifies_and_recommends_status_then_compile_gate(self) -> None:
        payload = self._refresh_timeout_payload(step_payload=self._unity_evidence("package_settle_timeout"))

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        recovery = verdict["refresh_timeout_recovery"]
        self.assertEqual("package_settle_timeout", recovery["timeout_classification"])
        self.assertEqual("unity_step_evidence", recovery["classification_source"])
        self.assertEqual("request_status_summary_then_compile_gate", recovery["recommended_next_action"])
        self.assertEqual("request_status_summary_then_compile_gate", verdict["recommended_next_action"])
        self.assertTrue(recovery["operation_may_have_completed"])
        self.assertIn("may have completed", recovery["note"])
        self.assertEqual(
            ["request-status-summary", "--project-root", "/tmp/FakeProject"],
            recovery["recovery_cli_args"],
        )
        self.assertEqual("unity_compile_player_scripts", recovery["compile_gate_tool"])
        self.assertEqual({"projectRoot": "/tmp/FakeProject"}, recovery["compile_gate_tool_arguments"])
        self.assertEqual("waiting_for_package_settle", recovery["settle_phase_at_timeout"])
        self.assertEqual("infrastructure_timeout", verdict["failure_class"])
        self.assertEqual("inconclusive", verdict["verdict"])

    def test_compile_churn_and_lost_accounting_evidence_are_preserved(self) -> None:
        for classification, phase in (
            ("compile_import_churn_timeout", "waiting_for_editor_idle"),
            ("lost_final_accounting", ""),
            ("idle_confirmation_incomplete", "waiting_for_stable_idle_ticks"),
            ("editor_busy_timeout", "waiting_for_editor_idle"),
        ):
            payload = self._refresh_timeout_payload(
                step_payload=self._unity_evidence(classification, settle_phase_at_timeout=phase)
            )

            verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

            recovery = verdict["refresh_timeout_recovery"]
            self.assertEqual(classification, recovery["timeout_classification"])
            self.assertEqual(phase, recovery["settle_phase_at_timeout"])
            self.assertEqual("request_status_summary_then_compile_gate", verdict["recommended_next_action"])

    def test_legacy_payload_without_evidence_still_guides_but_says_unclassified(self) -> None:
        payload = self._refresh_timeout_payload()

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        recovery = verdict["refresh_timeout_recovery"]
        self.assertEqual("unclassified_legacy_payload", recovery["timeout_classification"])
        self.assertEqual("none", recovery["classification_source"])
        self.assertEqual("unknown_at_summary_time", recovery["editor_reachability_after_timeout"])
        self.assertEqual("request_status_summary_then_compile_gate", verdict["recommended_next_action"])
        self.assertNotIn("settle_phase_at_timeout", recovery)

    def test_offline_host_health_overrides_step_evidence_as_editor_failure(self) -> None:
        payload = self._refresh_timeout_payload(
            step_payload=self._unity_evidence("lost_final_accounting", operation_may_have_completed=True),
            extra_payload_fields={"host_health_classification": "offline"},
        )

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        recovery = verdict["refresh_timeout_recovery"]
        self.assertEqual("editor_failure", recovery["timeout_classification"])
        self.assertEqual("host_health_classification", recovery["classification_source"])
        self.assertEqual("offline", recovery["editor_reachability_after_timeout"])
        self.assertEqual("recover_editor_session", recovery["recommended_next_action"])
        self.assertEqual("recover_editor_session", verdict["recommended_next_action"])
        self.assertIn("unproven", recovery["note"])
        self.assertEqual(
            ["ensure-ready", "--project-root", "/tmp/FakeProject", "--open-editor"],
            recovery["recovery_cli_args"],
        )
        self.assertNotIn("compile_gate_tool", recovery)

    def test_editor_relaunch_attribution_classifies_lost_final_accounting(self) -> None:
        payload = self._refresh_timeout_payload(
            extra_payload_fields={
                "editor_relaunched": True,
                "previous_editor_pid": 100,
                "current_editor_pid": 200,
                "bridge_generation_before": 3,
                "bridge_generation_after": 4,
                "cold_start_reason": "editor_process_lost",
            }
        )

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        recovery = verdict["refresh_timeout_recovery"]
        self.assertEqual("lost_final_accounting", recovery["timeout_classification"])
        self.assertEqual("editor_relaunch_attribution", recovery["classification_source"])
        self.assertEqual("request_status_summary_then_compile_gate", verdict["recommended_next_action"])

    def test_applied_mutation_settle_timeout_keeps_released_action(self) -> None:
        payload = self._refresh_timeout_payload(step_payload=self._unity_evidence("package_settle_timeout"))
        payload["steps"].insert(
            0,
            {
                "stepId": "set_profile",
                "kind": "project_defined_hook",
                "status": "passed",
                "outcome": "operation_succeeded",
                "payload_json": json.dumps({"outcome": "environment_applied"}),
            },
        )

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        self.assertEqual("applied_mutation_settle_timeout", verdict["failure_class"])
        self.assertEqual("verify_editor_settled_before_next_mutation", verdict["recommended_next_action"])
        recovery = verdict["refresh_timeout_recovery"]
        self.assertEqual("package_settle_timeout", recovery["timeout_classification"])
        self.assertEqual("request_status_summary_then_compile_gate", recovery["recommended_next_action"])

    def test_cleanup_refresh_timeout_keeps_cleanup_action(self) -> None:
        payload = self._refresh_timeout_payload(step_payload=self._unity_evidence("package_settle_timeout"))
        payload["steps"].insert(
            0,
            {"stepId": "work", "kind": "status", "status": "passed"},
        )
        payload["cleanup_start_index"] = 1

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        self.assertEqual("cleanup", verdict["failure_class"])
        self.assertEqual("inspect_cleanup_failure_and_restore_state", verdict["recommended_next_action"])
        self.assertIn("refresh_timeout_recovery", verdict)

    def test_non_refresh_failures_get_no_recovery_block(self) -> None:
        payload = {
            "project_root": "/tmp/FakeProject",
            "run_id": "run-other-failure",
            "scenario_name": "CompileOnly",
            "status": "failed",
            "terminal": True,
            "succeeded": False,
            "steps": [
                {
                    "stepId": "compile",
                    "kind": "compile_player_scripts",
                    "status": "failed",
                    "error_code": "compile_player_scripts_timeout",
                }
            ],
        }

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        self.assertNotIn("refresh_timeout_recovery", verdict)
        self.assertEqual(
            "verify_editor_settled_then_retry_or_increase_timeout",
            verdict["recommended_next_action"],
        )

    def test_explicit_recommended_next_action_is_not_overridden(self) -> None:
        payload = self._refresh_timeout_payload(
            step_payload=self._unity_evidence("package_settle_timeout"),
            extra_payload_fields={"recommended_next_action": "custom_operator_action"},
        )

        verdict = server_summaries.build_scenario_decision_verdict(payload, {"passed", "failed"})

        self.assertEqual("custom_operator_action", verdict["recommended_next_action"])
        self.assertIn("refresh_timeout_recovery", verdict)

    def test_result_summary_attaches_block_and_action_without_contradicting_mutation_summary(self) -> None:
        plain = self._refresh_timeout_payload(step_payload=self._unity_evidence("package_settle_timeout"))
        summary = server_summaries.build_scenario_result_summary(plain, {"passed", "failed"})
        self.assertEqual("request_status_summary_then_compile_gate", summary["recommended_next_action"])
        self.assertIn("refresh_timeout_recovery", summary)

        mutated = self._refresh_timeout_payload(step_payload=self._unity_evidence("package_settle_timeout"))
        mutated["steps"].insert(
            0,
            {
                "stepId": "set_profile",
                "kind": "project_defined_hook",
                "status": "passed",
                "outcome": "operation_succeeded",
                "payload_json": json.dumps({"outcome": "environment_applied"}),
            },
        )
        mutated_summary = server_summaries.build_scenario_result_summary(mutated, {"passed", "failed"})
        self.assertIn("applied_mutation_settle_summary", mutated_summary)
        self.assertNotIn("recommended_next_action", mutated_summary)

    def test_passed_scenario_never_carries_recovery_block(self) -> None:
        payload = self._refresh_timeout_payload(step_payload=self._unity_evidence("package_settle_timeout"))
        payload["status"] = "passed"
        payload["succeeded"] = True

        summary = server_summaries.build_scenario_result_summary(payload, {"passed", "failed"})

        self.assertNotIn("refresh_timeout_recovery", summary)


if __name__ == "__main__":
    unittest.main()
