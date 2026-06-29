import argparse
import contextlib
import io
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
import server_mcp_tools
import server_project_actions
import server_summaries


def get_subparser_choices(parser: argparse.ArgumentParser) -> set[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices.keys())
    return set()


class ServerProtocolAndParserTests(unittest.TestCase):
    def test_parser_contains_critical_subcommands(self) -> None:
        parser = server.build_parser()
        choices = get_subparser_choices(parser)

        self.assertTrue(
            {
                "bridge-state",
                "setup-plan",
                "setup-apply",
                "uninstall-plan",
                "uninstall-apply",
                "validate-setup",
                "install-test-framework",
                "license-capabilities",
                "request-status",
                "request-status-summary",
                "request-final-status",
                "request-cancel",
                "request-stale-cleanup",
                "request-scenario-results-list",
                "request-scenario-result-latest",
                "request-project-refresh",
                "project-action-list",
                "project-action-invoke",
                "artifact-register",
                "artifact-write-report",
                "request-install-test-framework",
                "verify-editor-closed",
                "request-edm4u-resolve",
                "request-sdk-dependency-verify",
                "project-discovery-report",
                "registry-context-report",
                "registry-prune-contexts",
                "request-compile",
                "request-build-player",
                "request-editmode-tests",
                "ensure-ready",
                "recover-editor-session",
                "batch-compile",
                "test-results-table",
                "artifact-probe",
                "maintenance-prune",
            }.issubset(choices)
        )

    def test_tools_list_includes_required_tool_surfaces(self) -> None:
        response = server.handle_json_rpc_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
        )

        tool_names = {
            tool["name"]
            for tool in response["result"]["tools"]
        }
        self.assertIn("unity_status_summary", tool_names)
        self.assertIn("xuunity_setup_plan", tool_names)
        self.assertIn("xuunity_setup_apply", tool_names)
        self.assertIn("xuunity_uninstall_plan", tool_names)
        self.assertIn("xuunity_uninstall_apply", tool_names)
        self.assertIn("xuunity_setup_validate", tool_names)
        self.assertIn("unity_license_capabilities", tool_names)
        self.assertIn("unity_package_install_test_framework", tool_names)
        self.assertIn("unity_request_final_status", tool_names)
        self.assertIn("unity_compile_build_config_matrix", tool_names)
        self.assertIn("unity_build_player", tool_names)
        self.assertIn("unity_edm4u_resolve", tool_names)
        self.assertIn("unity_sdk_dependency_verify", tool_names)
        self.assertIn("unity_console_grep", tool_names)
        self.assertIn("unity_loading_timing", tool_names)
        self.assertIn("unity_scenario_run_and_wait", tool_names)
        self.assertIn("unity_scenario_results_list", tool_names)
        self.assertIn("unity_scenario_result_latest", tool_names)
        self.assertIn("unity_project_action_list", tool_names)
        self.assertIn("unity_project_action_invoke", tool_names)
        self.assertIn("unity_artifact_register", tool_names)
        self.assertIn("unity_artifact_write_report", tool_names)
        compile_tool = next(tool for tool in response["result"]["tools"] if tool["name"] == "unity_compile_player_scripts")
        self.assertIn("includeFullPayload", compile_tool["inputSchema"]["properties"])

    def test_compile_tool_returns_compact_payload_by_default(self) -> None:
        invoke_calls: list[tuple[str, dict[str, object], int]] = []

        def fake_invoke_bridge(
            project_root_value: str,
            operation: str,
            operation_args: dict[str, object],
            timeout_ms: int,
        ) -> dict[str, object]:
            invoke_calls.append((operation, dict(operation_args), timeout_ms))
            return {
                "status": "ok",
                "payload_type": "unity.compile.player_scripts",
                "payload_json": json.dumps(
                    {
                        "name": "Standalone",
                        "target": "StandaloneOSX",
                        "status": "passed",
                        "error_count": 0,
                        "warning_count": 1,
                        "compiled_assembly_count": 70,
                        "duration_seconds": 4.25,
                        "post_settle_compile": "passed",
                        "post_settle_error_count": 0,
                        "post_settle_diagnostics": [],
                        "settle_phase": "settled",
                        "completion_basis": "unity_compile_settle_watcher",
                        "artifact_manifest": {
                            "base_dir": "/tmp/artifacts",
                            "groups": {"logs": [{"path": "/tmp/artifacts/editor.log"}]},
                        },
                    }
                ),
                "_xuunity_lifecycle": {
                    "operation": "unity.compile.player_scripts",
                    "idle_wait_before": {"health_status": "healthy"},
                    "idle_wait_after": {"health_status": "healthy"},
                },
            }

        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "invoke_bridge", side_effect=fake_invoke_bridge),
        ):
            response = server.handle_json_rpc_message(
                {
                    "jsonrpc": "2.0",
                    "id": 22,
                    "method": "tools/call",
                    "params": {
                        "name": "unity_compile_player_scripts",
                        "arguments": {
                            "projectRoot": "/tmp/FakeProject",
                            "target": "StandaloneOSX",
                            "timeoutMs": 180000,
                        },
                    },
                },
                {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
            )

        structured = response["result"]["structuredContent"]
        self.assertFalse(response["result"]["isError"])
        self.assertEqual("compact_operation", structured["payload_mode"])
        self.assertEqual("unity.compile.player_scripts", structured["operation"])
        self.assertEqual("passed", structured["status"])
        self.assertEqual("passed", structured["post_settle_compile"])
        self.assertEqual(0, structured["post_settle_error_count"])
        self.assertEqual(1, structured["artifact_count"])
        self.assertNotIn("_xuunity_lifecycle", structured)
        self.assertTrue(structured["full_payload_available"])
        self.assertEqual({"includeFullPayload": True}, structured["full_payload_tool_arguments"])
        self.assertEqual(("unity.compile.player_scripts", {"target": "StandaloneOSX"}, 180000), invoke_calls[0])

    def test_compile_tool_full_payload_opt_in_preserves_lifecycle(self) -> None:
        invoke_calls: list[tuple[str, dict[str, object], int]] = []

        def fake_invoke_bridge(
            project_root_value: str,
            operation: str,
            operation_args: dict[str, object],
            timeout_ms: int,
        ) -> dict[str, object]:
            invoke_calls.append((operation, dict(operation_args), timeout_ms))
            return {
                "status": "ok",
                "payload_type": "unity.compile.player_scripts",
                "payload_json": json.dumps({"status": "passed", "error_count": 0}),
                "_xuunity_lifecycle": {
                    "operation": "unity.compile.player_scripts",
                    "idle_wait_after": {"health_status": "healthy"},
                },
            }

        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "invoke_bridge", side_effect=fake_invoke_bridge),
        ):
            response = server.handle_json_rpc_message(
                {
                    "jsonrpc": "2.0",
                    "id": 23,
                    "method": "tools/call",
                    "params": {
                        "name": "unity_compile_player_scripts",
                        "arguments": {
                            "projectRoot": "/tmp/FakeProject",
                            "target": "StandaloneOSX",
                            "includeFullPayload": True,
                        },
                    },
                },
                {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
            )

        structured = response["result"]["structuredContent"]
        self.assertFalse(response["result"]["isError"])
        self.assertEqual("passed", structured["status"])
        self.assertIn("_xuunity_lifecycle", structured)
        self.assertNotIn("payload_mode", structured)
        self.assertEqual(("unity.compile.player_scripts", {"target": "StandaloneOSX"}, 180000), invoke_calls[0])

    def test_build_config_compile_tool_returns_compact_matrix_by_default(self) -> None:
        invoke_calls: list[tuple[str, dict[str, object], int]] = []
        fake_plan = {
            "assetPath": "Assets/BuildConfig.asset",
            "profiles": ["Dev"],
            "matrixArgs": {
                "configurations": [
                    {"name": "DevAndroid", "target": "Android"},
                ],
            },
        }

        def fake_invoke_bridge(
            project_root_value: str,
            operation: str,
            operation_args: dict[str, object],
            timeout_ms: int,
        ) -> dict[str, object]:
            invoke_calls.append((operation, dict(operation_args), timeout_ms))
            return {
                "status": "ok",
                "payload_type": "unity.compile.matrix",
                "payload_json": json.dumps(
                    {
                        "total": 1,
                        "passed": 1,
                        "failed": 0,
                        "post_settle_compile": "passed",
                        "post_settle_error_count": 0,
                        "settle_phase": "settled",
                        "completion_basis": "unity_compile_settle_watcher",
                    }
                ),
                "_xuunity_lifecycle": {
                    "operation": "unity.compile.matrix",
                    "idle_wait_after": {"health_status": "healthy"},
                },
            }

        response = server_mcp_tools.call_unity_compile_build_config_matrix_tool(
            {
                "projectRoot": "/tmp/FakeProject",
                "profiles": ["Dev"],
                "timeoutMs": 300000,
            },
            tool_invocation_error_type=server.ToolInvocationError,
            ensure_project_root=lambda value: Path(value),
            resolve_operation_timeout_ms=lambda project_root, operation, value, default: int(value or default),
            build_compile_matrix_args_from_build_config=lambda **kwargs: fake_plan,
            invoke_bridge=fake_invoke_bridge,
            build_tool_error_payload=server.build_tool_error_payload,
            bridge_response_to_tool_result=server.bridge_response_to_tool_result,
        )

        structured = response["structuredContent"]
        matrix = structured["matrix"]
        self.assertFalse(response["isError"])
        self.assertEqual("Assets/BuildConfig.asset", structured["build_config_asset"])
        self.assertEqual(["Dev"], structured["profiles"])
        self.assertEqual("compact_operation", matrix["payload_mode"])
        self.assertEqual("unity.compile.matrix", matrix["operation"])
        self.assertEqual("passed", matrix["post_settle_compile"])
        self.assertNotIn("_xuunity_lifecycle", matrix)
        self.assertEqual(("unity.compile.matrix", fake_plan["matrixArgs"], 300000), invoke_calls[0])

    def test_setup_apply_parser_accepts_explicit_project_roots(self) -> None:
        parser = server.build_parser()
        args = parser.parse_args(
            [
                "setup-apply",
                "--plan-file",
                "/tmp/plan.json",
                "--project-root",
                "/tmp/ProjectA",
                "--project-root",
                "/tmp/ProjectB",
                "--yes",
            ]
        )

        self.assertEqual("setup-apply", args.command)
        self.assertEqual(["/tmp/ProjectA", "/tmp/ProjectB"], args.project_root)
        self.assertTrue(args.yes)

    def test_uninstall_parser_accepts_modes_and_client_scope(self) -> None:
        parser = server.build_parser()
        plan_args = parser.parse_args(
            [
                "uninstall-plan",
                "--mode",
                "full-reset-current-user",
                "--project-root",
                "/tmp/ProjectA",
                "--client",
                "codex",
                "--include-other-client-helpers",
            ]
        )
        apply_args = parser.parse_args(
            [
                "uninstall-apply",
                "--plan-file",
                "/tmp/uninstall-plan.json",
                "--yes",
            ]
        )

        self.assertEqual("uninstall-plan", plan_args.command)
        self.assertEqual("full-reset-current-user", plan_args.mode)
        self.assertEqual(["/tmp/ProjectA"], plan_args.project_root)
        self.assertEqual("codex", plan_args.client)
        self.assertTrue(plan_args.include_other_client_helpers)
        self.assertEqual("uninstall-apply", apply_args.command)
        self.assertTrue(apply_args.yes)

        alias_args = parser.parse_args(
            [
                "uninstall-plan",
                "--mode",
                "current-user-reset",
                "--client",
                "codex",
            ]
        )
        self.assertEqual("current-user-reset", alias_args.mode)

    def test_project_action_catalog_parser_resolves_aliases_and_hook_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_path = Path(temp_dir) / "project_actions.yaml"
            catalog_path.write_text(
                """
schemaVersion: xuunity.project-actions.v1
project: FakeProject
hookName: ""
actions:
  project.safe:
    aliases: [safe]
    hookName: example.project
    payload:
      mode: string
    mutates: []
    evidence:
      - compact_result
    validationModes:
      - project_action_contract
""".strip(),
                encoding="utf-8",
            )

            catalog = server_project_actions.load_project_action_catalog(
                Path(temp_dir) / "FakeProject",
                str(catalog_path),
            )

        listed = server_project_actions.project_action_catalog_payload(catalog)
        self.assertEqual("xuunity.project-actions.v1", listed["schema_version"])
        self.assertEqual(["project.safe"], listed["available_actions"])
        self.assertEqual([], listed["validation_errors"])
        action = server_project_actions.resolve_project_action(catalog, "safe")
        self.assertEqual("project.safe", action["action_id"])
        self.assertEqual("safe", action["resolved_by_alias"])
        self.assertEqual("example.project", action["hook_name"])

    def test_project_action_list_tool_returns_catalog_without_editor_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "FakeProject"
            project_root.mkdir()
            catalog_path = Path(temp_dir) / "project_actions.yaml"
            catalog_path.write_text(
                """
schemaVersion: xuunity.project-actions.v1
project: FakeProject
hookName: example.default
actions:
  project.safe:
    aliases:
      - safe
    payload: {}
    mutates: []
    evidence:
      - compact_result
    validationModes:
      - project_action_contract
""".strip(),
                encoding="utf-8",
            )

            with mock.patch.object(server, "ensure_project_root", return_value=project_root):
                response = server.handle_json_rpc_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 20,
                        "method": "tools/call",
                        "params": {
                            "name": "unity_project_action_list",
                            "arguments": {
                                "projectRoot": str(project_root),
                                "catalogPath": str(catalog_path),
                            },
                        },
                    },
                    {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
                )

        result = response["result"]
        self.assertFalse(result["isError"])
        self.assertEqual("unity_project_action_list", result["structuredContent"]["action"])
        self.assertEqual(["project.safe"], result["structuredContent"]["available_actions"])
        self.assertEqual("example.default", result["structuredContent"]["actions"][0]["hook_name"])

    def test_project_action_invoke_tool_runs_typed_action_scenario_and_compact_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "FakeProject"
            project_root.mkdir()
            catalog_path = Path(temp_dir) / "project_actions.yaml"
            catalog_path.write_text(
                """
schemaVersion: xuunity.project-actions.v1
project: FakeProject
hookName: ""
actions:
  project.safe:
    aliases:
      - safe
    hookName: example.project
    payload:
      foo: string
    mutates: []
    evidence:
      - changed_file_count
    validationModes:
      - project_action_contract
""".strip(),
                encoding="utf-8",
            )

            invoke_calls: list[tuple[str, dict[str, object], int]] = []

            def fake_invoke_bridge(
                project_root_value: str,
                operation: str,
                operation_args: dict[str, object],
                timeout_ms: int,
            ) -> dict[str, object]:
                invoke_calls.append((operation, dict(operation_args), timeout_ms))
                return {
                    "status": "ok",
                    "payload_type": "unity.scenario.run",
                    "payload_json": json.dumps(
                        {
                            "project_root": str(project_root),
                            "run_id": "run-1",
                            "scenario_name": "TypedActionSmoke",
                            "status": "queued",
                        }
                    ),
                }

            with (
                mock.patch.object(server, "ensure_project_root", return_value=project_root),
                mock.patch.object(server, "invoke_bridge", side_effect=fake_invoke_bridge),
                mock.patch.object(
                    server,
                    "wait_for_scenario_result",
                    return_value={
                        "project_root": str(project_root),
                        "run_id": "run-1",
                        "scenario_name": "TypedActionSmoke",
                        "status": "passed",
                        "total_steps": 1,
                        "passed_steps": 1,
                        "failed_steps": 0,
                        "skipped_steps": 0,
                        "steps": [
                            {
                                "stepId": "invoke_project_action",
                                "kind": "project_defined_hook",
                                "status": "passed",
                                "outcome": "hook_succeeded",
                                "hook_name": "example.project",
                                "payload_json": json.dumps(
                                    {
                                        "outcome": "done",
                                        "changed_file_count": 2,
                                        "api_token": "do-not-surface",
                                    }
                                ),
                            }
                        ],
                    },
                ),
                mock.patch.object(
                    server,
                    "refresh_project_context",
                    return_value=mock.Mock(discovery_details={}, last_bridge_state={}),
                ),
            ):
                response = server.handle_json_rpc_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 21,
                        "method": "tools/call",
                        "params": {
                            "name": "unity_project_action_invoke",
                            "arguments": {
                                "projectRoot": str(project_root),
                                "catalogPath": str(catalog_path),
                                "actionId": "safe",
                                "payload": {"foo": "bar"},
                                "scenarioName": "TypedActionSmoke",
                            },
                        },
                    },
                    {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
                )

        result = response["result"]
        self.assertFalse(result["isError"])
        structured = result["structuredContent"]
        self.assertEqual("unity_project_action_invoke", structured["action"])
        self.assertEqual("project.safe", structured["action_id"])
        self.assertEqual("safe", structured["resolved_by_alias"])
        self.assertTrue(structured["succeeded"])
        hook_summary = structured["project_defined_hook_summary"]["hooks"][0]
        self.assertEqual("done", hook_summary["outcome"])
        self.assertEqual(2, hook_summary["payload_scalars"]["changed_file_count"])
        self.assertNotIn("api_token", hook_summary.get("payload_scalars", {}))

        self.assertEqual(1, len(invoke_calls))
        operation, scenario_args, timeout_ms = invoke_calls[0]
        self.assertEqual("unity.scenario.run", operation)
        self.assertEqual(15000, timeout_ms)
        scenario = scenario_args["scenario"]
        hook_payload_json = scenario["steps"][0]["hookPayloadJson"]
        hook_payload = json.loads(hook_payload_json)
        self.assertEqual("project.safe", hook_payload["action"])
        self.assertEqual("bar", hook_payload["foo"])

    def test_project_action_invoke_tool_requires_explicit_mutation_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "FakeProject"
            project_root.mkdir()
            catalog_path = Path(temp_dir) / "project_actions.yaml"
            catalog_path.write_text(
                """
schemaVersion: xuunity.project-actions.v1
project: FakeProject
hookName: example.project
actions:
  project.mutating:
    payload: {}
    mutates:
      - PlayerPrefs
    validationModes:
      - project_action_contract
""".strip(),
                encoding="utf-8",
            )

            with (
                mock.patch.object(server, "ensure_project_root", return_value=project_root),
                mock.patch.object(server, "invoke_bridge") as invoke_mock,
            ):
                response = server.handle_json_rpc_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 22,
                        "method": "tools/call",
                        "params": {
                            "name": "unity_project_action_invoke",
                            "arguments": {
                                "projectRoot": str(project_root),
                                "catalogPath": str(catalog_path),
                                "actionId": "project.mutating",
                            },
                        },
                    },
                    {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
                )

        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(
            "project_action_mutation_approval_required",
            result["structuredContent"]["error"]["code"],
        )
        invoke_mock.assert_not_called()

    def test_scenario_run_and_wait_expands_project_action_steps_before_unity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            project_root = workspace_root / "FakeProject"
            project_root.mkdir()
            catalog_path = (
                workspace_root
                / "AIOutput"
                / "Projects"
                / "FakeProject"
                / "Operations"
                / "XUUnityLightUnityMcp"
                / "project_actions.yaml"
            )
            catalog_path.parent.mkdir(parents=True)
            catalog_path.write_text(
                """
schemaVersion: xuunity.project-actions.v1
project: FakeProject
hookName: ""
actions:
  localization.list_actions:
    hookName: example.localization
    payload: {}
    mutates: []
    validationModes:
      - localization_pipeline
""".strip(),
                encoding="utf-8",
            )

            invoke_calls: list[tuple[str, dict[str, object], int]] = []

            def fake_invoke_bridge(
                project_root_value: str,
                operation: str,
                operation_args: dict[str, object],
                timeout_ms: int,
            ) -> dict[str, object]:
                invoke_calls.append((operation, dict(operation_args), timeout_ms))
                return {
                    "status": "ok",
                    "payload_type": "unity.scenario.run",
                    "payload_json": json.dumps(
                        {
                            "project_root": str(project_root),
                            "run_id": "run-typed-scenario",
                            "scenario_name": "TypedLocalizationScenario",
                            "status": "queued",
                        }
                    ),
                }

            with (
                mock.patch.object(server, "ensure_project_root", return_value=project_root),
                mock.patch.object(server, "invoke_bridge", side_effect=fake_invoke_bridge),
                mock.patch.object(
                    server,
                    "wait_for_scenario_result",
                    return_value={
                        "project_root": str(project_root),
                        "run_id": "run-typed-scenario",
                        "scenario_name": "TypedLocalizationScenario",
                        "status": "passed",
                        "succeeded": True,
                        "terminal": True,
                        "total_steps": 1,
                        "passed_steps": 1,
                        "failed_steps": 0,
                        "skipped_steps": 0,
                    },
                ),
            ):
                response = server.handle_json_rpc_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 25,
                        "method": "tools/call",
                        "params": {
                            "name": "unity_scenario_run_and_wait",
                            "arguments": {
                                "projectRoot": str(project_root),
                                "scenario": {
                                    "name": "TypedLocalizationScenario",
                                    "steps": [
                                        {
                                            "stepId": "localization_list_actions",
                                            "kind": "project_action",
                                            "actionId": "localization.list_actions",
                                            "payload": {},
                                        }
                                    ],
                                },
                            },
                        },
                    },
                    {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
                )

        self.assertFalse(response["result"]["isError"])
        self.assertEqual(1, len(invoke_calls))
        operation, scenario_args, _ = invoke_calls[0]
        self.assertEqual("unity.scenario.run", operation)
        sent_step = scenario_args["scenario"]["steps"][0]
        self.assertEqual("project_defined_hook", sent_step["kind"])
        self.assertEqual("example.localization", sent_step["hookName"])
        self.assertEqual(
            {"action": "localization.list_actions"},
            json.loads(sent_step["hookPayloadJson"]),
        )

    def test_scenario_run_normalizes_poll_until_operation_payloads_before_unity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "FakeProject"
            project_root.mkdir()
            invoke_calls: list[tuple[str, dict[str, object], int]] = []

            def fake_invoke_bridge(
                project_root_value: str,
                operation: str,
                operation_args: dict[str, object],
                timeout_ms: int,
            ) -> dict[str, object]:
                invoke_calls.append((operation, dict(operation_args), timeout_ms))
                return {
                    "status": "ok",
                    "payload_type": "unity.scenario.run",
                    "payload_json": json.dumps(
                        {
                            "project_root": str(project_root),
                            "run_id": "run-poll",
                            "scenario_name": "PollUntilSmoke",
                            "status": "queued",
                        }
                    ),
                }

            with (
                mock.patch.object(server, "ensure_project_root", return_value=project_root),
                mock.patch.object(server, "invoke_bridge", side_effect=fake_invoke_bridge),
            ):
                response = server.handle_json_rpc_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 230,
                        "method": "tools/call",
                        "params": {
                            "name": "unity_scenario_run",
                            "arguments": {
                                "projectRoot": str(project_root),
                                "scenario": {
                                    "name": "PollUntilSmoke",
                                    "steps": [
                                        {
                                            "stepId": "flow",
                                            "operation": "project_defined_hook_poll_until",
                                            "hookName": "example.ui_smoke",
                                            "startPayload": {"action": "start_flow"},
                                            "pollPayload": {"action": "snapshot_flow"},
                                            "passWhen": "payload.status == 'passed'",
                                            "failWhen": "payload.status == 'failed'",
                                            "continueWhen": "payload.status == 'running'",
                                            "intervalSeconds": 2,
                                            "timeoutSeconds": 180,
                                        }
                                    ],
                                },
                            },
                        },
                    },
                    {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
                )

        self.assertFalse(response["result"]["isError"])
        self.assertEqual(1, len(invoke_calls))
        operation, scenario_args, _ = invoke_calls[0]
        self.assertEqual("unity.scenario.run", operation)
        step = scenario_args["scenario"]["steps"][0]
        self.assertEqual("project_defined_hook_poll_until", step["kind"])
        self.assertEqual({"action": "start_flow"}, json.loads(step["startPayloadJson"]))
        self.assertEqual({"action": "snapshot_flow"}, json.loads(step["pollPayloadJson"]))
        self.assertNotIn("startPayload", step)
        self.assertNotIn("pollPayload", step)

    def test_scenario_summary_promotes_poll_until_terminal_fields_and_cleanup(self) -> None:
        summary = server_summaries.build_scenario_result_summary(
            {
                "project_root": "/tmp/FakeProject",
                "run_id": "run-poll",
                "scenario_name": "PollUntilSmoke",
                "status": "failed",
                "cleanup_start_index": 1,
                "steps": [
                    {
                        "stepId": "flow",
                        "kind": "project_defined_hook_poll_until",
                        "status": "failed",
                        "outcome": "hook_poll_until_failed",
                        "hook_name": "example.ui_smoke",
                        "terminal_status": "failed",
                        "failure_class": "product",
                        "poll_count": 3,
                        "promote_payload_fields": ["status", "failure_class", "selected_tab", "api_token"],
                        "payload_json": json.dumps(
                            {
                                "status": "failed",
                                "failure_class": "product",
                                "selected_tab": "Store",
                                "api_token": "do-not-surface",
                            }
                        ),
                        "terminal_screenshot_payload_json": json.dumps({"file_path": "/tmp/smoke.png"}),
                        "error_code": "ui_assertion_failed",
                    },
                    {
                        "stepId": "cleanup",
                        "kind": "project_defined_hook",
                        "status": "passed",
                        "outcome": "hook_succeeded",
                        "hook_name": "example.ui_smoke",
                        "payload_json": json.dumps({"status": "cleaned"}),
                    },
                ],
            },
            {"passed", "failed"},
        )

        hook_summary = summary["project_defined_hook_summary"]["hooks"][0]
        self.assertEqual("project_defined_hook_poll_until", hook_summary["kind"])
        self.assertEqual("failed", hook_summary["terminal_status"])
        self.assertEqual("product", hook_summary["failure_class"])
        self.assertEqual(3, hook_summary["poll_count"])
        self.assertEqual("Store", hook_summary["promoted_payload_scalars"]["selected_tab"])
        self.assertNotIn("api_token", hook_summary["promoted_payload_scalars"])
        self.assertEqual("/tmp/smoke.png", hook_summary["screenshot_path"])
        self.assertEqual("passed", summary["cleanup_summary"]["cleanup_result"])

    def test_scenario_project_action_steps_accept_payload_json_escape_hatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            project_root = workspace_root / "FakeProject"
            project_root.mkdir()
            catalog_path = (
                workspace_root
                / "AIOutput"
                / "Projects"
                / "FakeProject"
                / "Operations"
                / "XUUnityLightUnityMcp"
                / "project_actions.yaml"
            )
            catalog_path.parent.mkdir(parents=True)
            catalog_path.write_text(
                """
schemaVersion: xuunity.project-actions.v1
project: FakeProject
hookName: example.localization
actions:
  localization.scan:
    payload: {}
    mutates:
      - repo-level reports
    validationModes:
      - localization_pipeline
""".strip(),
                encoding="utf-8",
            )

            normalized = server_project_actions.normalize_project_action_scenario(
                project_root=project_root,
                scenario={
                    "name": "PayloadJsonScenario",
                    "steps": [
                        {
                            "stepId": "localization_scan",
                            "kind": "project_action",
                            "actionId": "localization.scan",
                            "allowMutating": True,
                            "payloadJson": "{\"target_language\":\"pt-BR\"}",
                        }
                    ],
                },
            )

        sent_step = normalized["steps"][0]
        self.assertEqual("project_defined_hook", sent_step["kind"])
        self.assertNotIn("payloadJson", sent_step)
        self.assertEqual(
            {"target_language": "pt-BR", "action": "localization.scan"},
            json.loads(sent_step["hookPayloadJson"]),
        )

    def test_scenario_project_action_steps_require_mutation_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            project_root = workspace_root / "FakeProject"
            project_root.mkdir()
            catalog_path = (
                workspace_root
                / "AIOutput"
                / "Projects"
                / "FakeProject"
                / "Operations"
                / "XUUnityLightUnityMcp"
                / "project_actions.yaml"
            )
            catalog_path.parent.mkdir(parents=True)
            catalog_path.write_text(
                """
schemaVersion: xuunity.project-actions.v1
project: FakeProject
hookName: example.localization
actions:
  localization.scan:
    payload: {}
    mutates:
      - repo-level reports
    validationModes:
      - localization_pipeline
""".strip(),
                encoding="utf-8",
            )

            with (
                mock.patch.object(server, "ensure_project_root", return_value=project_root),
                mock.patch.object(server, "invoke_bridge") as invoke_mock,
            ):
                response = server.handle_json_rpc_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 26,
                        "method": "tools/call",
                        "params": {
                            "name": "unity_scenario_validate",
                            "arguments": {
                                "projectRoot": str(project_root),
                                "scenario": {
                                    "name": "TypedLocalizationMutationGuard",
                                    "steps": [
                                        {
                                            "stepId": "localization_scan",
                                            "kind": "project_action",
                                            "actionId": "localization.scan",
                                        }
                                    ],
                                },
                            },
                        },
                    },
                    {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
                )

        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(
            "project_action_mutation_approval_required",
            result["structuredContent"]["error"]["code"],
        )
        invoke_mock.assert_not_called()

    def test_artifact_write_report_tool_writes_repo_report_and_registry_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            project_root = workspace_root / "FakeProject"
            project_root.mkdir()

            with mock.patch.object(server, "ensure_project_root", return_value=project_root):
                response = server.handle_json_rpc_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 23,
                        "method": "tools/call",
                        "params": {
                            "name": "unity_artifact_write_report",
                            "arguments": {
                                "projectRoot": str(project_root),
                                "workspaceRoot": str(workspace_root),
                                "content": "# Report\n",
                                "category": "Localization",
                                "relativePath": "smoke/report.md",
                                "kind": "localization_report",
                                "producer": "test",
                                "artifactSchemaVersion": "demo.v1",
                                "language": "pt-BR",
                                "metadata": {"api_token": "secret", "count": 1},
                            },
                        },
                    },
                    {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
                )

            result = response["result"]
            self.assertFalse(result["isError"])
            structured = result["structuredContent"]
            self.assertEqual("repo_report", structured["destination"])
            self.assertFalse(structured["unity_imported"])
            self.assertEqual("AIOutput/Projects/FakeProject/Reports/Localization/smoke/report.md", structured["repo_relative_path"].replace('\\', '/'))
            self.assertEqual("localization_report", structured["kind"])
            self.assertEqual("demo.v1", structured["artifact_schema_version"])
            self.assertEqual("pt-BR", structured["language"])
            self.assertEqual("[REDACTED]", structured["metadata"]["api_token"])
            self.assertEqual(1, structured["metadata"]["count"])

            report_path = Path(structured["path"])
            self.assertEqual("# Report\n", report_path.read_text(encoding="utf-8"))
            registry_path = Path(structured["registry_path"])
            registry_lines = registry_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(1, len(registry_lines))
            registry_record = json.loads(registry_lines[0])
            self.assertEqual(structured["path"], registry_record["path"])
            self.assertEqual("[REDACTED]", registry_record["metadata"]["api_token"])

    def test_artifact_register_tool_requires_unity_assets_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_root = Path(temp_dir)
            project_root = workspace_root / "FakeProject"
            project_root.mkdir()

            with mock.patch.object(server, "ensure_project_root", return_value=project_root):
                response = server.handle_json_rpc_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 24,
                        "method": "tools/call",
                        "params": {
                            "name": "unity_artifact_register",
                            "arguments": {
                                "projectRoot": str(project_root),
                                "workspaceRoot": str(workspace_root),
                                "path": "Assets/AIOutput/report.md",
                                "destination": "unity_asset",
                            },
                        },
                    },
                    {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
                )

        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(
            "artifact_unity_asset_approval_required",
            result["structuredContent"]["error"]["code"],
        )

    def test_tools_call_status_summary_happy_path(self) -> None:
        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(
                server,
                "invoke_bridge",
                return_value={
                    "status": "ok",
                    "payload_type": "unity.status",
                    "payload_json": (
                        '{"editor_running": true, "mcp_reachable": true, '
                        '"health_status": "healthy", "playmode_state": "edit"}'
                    ),
                },
            ),
            mock.patch.object(
                server,
                "current_project_context_bridge_state",
                return_value={
                    "bridge_generation": 7,
                    "bridge_session_id": "session-a",
                    "transport": "tcp_loopback",
                    "transport_listener_state": "listening",
                    "pending_request_count": 0,
                    "health_status": "healthy",
                },
            ),
            mock.patch.object(
                server,
                "refresh_project_context",
                return_value=mock.Mock(
                    last_bridge_state={},
                    discovery_details={
                        "host_health_classification": "fresh",
                        "host_health_reason": "heartbeat_fresh",
                        "host_health_recommended_next_action": "none",
                        "host_health_termination_policy": "observe_only",
                        "host_health_heartbeat_age_seconds": 1.25,
                        "host_health_busy_reason": "idle",
                        "host_health_progress_evidence": [],
                        "anr_classification": "none",
                        "discovery_classification": "bridge_live",
                        "reconciliation_case": "bridge_state_authoritative",
                        "reconciliation_status": "healthy",
                        "detected_editor_count": 1,
                        "detected_editor_pids": [1234],
                        "transport_state": {"selection_scope": "per_project_context", "active_transport": "tcp_loopback"},
                        "state_groups": {"bridge_identity": {"bridge_generation": 7}},
                    },
                ),
            ),
            mock.patch.object(server, "pid_is_alive", return_value=True),
            mock.patch.object(server, "heartbeat_age_seconds", return_value=1.25),
            mock.patch.object(server, "derive_busy_reason", return_value="idle"),
            mock.patch.object(server, "summarize_state_for_error", return_value="ok"),
        ):
            response = server.handle_json_rpc_message(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "unity_status_summary",
                        "arguments": {"projectRoot": "/tmp/FakeProject", "timeoutMs": 5000},
                    },
                },
                {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
            )

        result = response["result"]
        self.assertFalse(result["isError"])
        self.assertEqual("unity_status_summary", result["structuredContent"]["action"])
        self.assertEqual(7, result["structuredContent"]["bridge_generation"])
        self.assertEqual("session-a", result["structuredContent"]["bridge_session_id"])
        self.assertEqual("healthy", result["structuredContent"]["health_status"])
        self.assertEqual("idle", result["structuredContent"]["busy_reason"])
        self.assertEqual("fresh", result["structuredContent"]["host_health_classification"])
        self.assertEqual("bridge_live", result["structuredContent"]["discovery_classification"])
        self.assertEqual("bridge_state_authoritative", result["structuredContent"]["reconciliation_case"])
        self.assertEqual("tcp_loopback", result["structuredContent"]["transport_state"]["active_transport"])
        self.assertEqual(7, result["structuredContent"]["state_groups"]["bridge_identity"]["bridge_generation"])

    def test_tools_call_status_summary_falls_back_to_discovery_when_editor_is_offline(self) -> None:
        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(
                server,
                "invoke_bridge",
                side_effect=server.ToolInvocationError(
                    "editor_not_running",
                    "Unity editor is not running for this project.",
                ),
            ),
            mock.patch.object(server, "current_project_context_bridge_state", return_value={"transport": "tcp_loopback"}),
            mock.patch.object(
                server,
                "refresh_project_context",
                return_value=mock.Mock(
                    last_bridge_state={"transport": "tcp_loopback"},
                    discovery_details={
                        "discovery_classification": "stale_state",
                        "discovery_reason": "state_files_present_without_live_project_process",
                        "authoritative_state_source": "state_files",
                        "reconciliation_case": "stale_bridge_state",
                        "reconciliation_status": "offline",
                        "reconciliation_reason": "bridge_state_present_but_editor_pid_not_alive",
                        "reconciliation_recommended_next_action": "recover_editor_session",
                        "detected_editor_count": 0,
                        "detected_editor_pids": [],
                        "bridge_state_live": False,
                        "host_session_live": False,
                        "active_transport": "tcp_loopback",
                    },
                ),
            ),
            mock.patch.object(server, "pid_is_alive", return_value=False),
            mock.patch.object(server, "heartbeat_age_seconds", return_value=None),
            mock.patch.object(server, "derive_busy_reason", return_value="idle"),
            mock.patch.object(server, "summarize_state_for_error", return_value="offline"),
        ):
            response = server.handle_json_rpc_message(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "unity_status_summary",
                        "arguments": {"projectRoot": "/tmp/FakeProject", "timeoutMs": 5000},
                    },
                },
                {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
            )

        result = response["result"]
        self.assertFalse(result["isError"])
        self.assertEqual("stale_bridge_state", result["structuredContent"]["reconciliation_case"])
        self.assertEqual("offline", result["structuredContent"]["reconciliation_status"])
        self.assertEqual("recover_editor_session", result["structuredContent"]["reconciliation_recommended_next_action"])

    def test_tools_call_scenario_result_summary_falls_back_to_discovery_when_editor_is_offline(self) -> None:
        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(
                server,
                "invoke_bridge",
                side_effect=server.ToolInvocationError(
                    "editor_not_running",
                    "Unity editor is not running for this project.",
                ),
            ),
            mock.patch.object(
                server,
                "refresh_project_context",
                return_value=mock.Mock(
                    last_bridge_state={"transport": "tcp_loopback"},
                    discovery_details={
                        "discovery_classification": "stale_state",
                        "discovery_reason": "state_files_present_without_live_project_process",
                        "authoritative_state_source": "state_files",
                        "reconciliation_case": "stale_bridge_state",
                        "reconciliation_status": "offline",
                        "reconciliation_reason": "bridge_state_present_but_editor_pid_not_alive",
                        "reconciliation_recommended_next_action": "recover_editor_session",
                        "detected_editor_count": 0,
                        "detected_editor_pids": [],
                    },
                ),
            ),
        ):
            response = server.handle_json_rpc_message(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "unity_scenario_result_summary",
                        "arguments": {
                            "projectRoot": "/tmp/FakeProject",
                            "scenarioName": "SampleScenario",
                            "timeoutMs": 5000,
                        },
                    },
                },
                {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
            )

        result = response["result"]
        self.assertFalse(result["isError"])
        self.assertEqual("offline", result["structuredContent"]["status"])
        self.assertEqual("stale_bridge_state", result["structuredContent"]["reconciliation_case"])
        self.assertEqual("recover_editor_session", result["structuredContent"]["recommended_next_action"])
        self.assertEqual("editor_not_running", result["structuredContent"]["offline_error_code"])

    def test_recover_editor_session_reports_batch_lane_conflict_without_claiming_compile_red(self) -> None:
        args = argparse.Namespace(
            project_root="/tmp/FakeProject",
            timeout_ms=180000,
            close_timeout_ms=45000,
            open_editor=False,
            force_compile_probe=True,
            heartbeat_max_age_seconds=10,
            startup_policy="fail_fast_on_interactive_compile_block",
        )
        discovery_initial = {
            "reconciliation_case": "stale_bridge_state",
            "detected_editor_pids": [],
            "editor_log_diagnosis": {},
        }
        discovery_after_clear = {
            "reconciliation_case": "host_launchable_not_active",
            "detected_editor_pids": [],
            "editor_log_diagnosis": {},
        }
        emitted_payloads: list[dict[str, object]] = []

        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "refresh_project_context"),
            mock.patch.object(
                server,
                "build_project_discovery_report",
                side_effect=[
                    discovery_initial,
                    discovery_initial,
                    discovery_after_clear,
                    discovery_after_clear,
                ],
            ),
            mock.patch.object(server, "current_project_context_host_session_state", return_value={}),
            mock.patch.object(server, "clear_stale_bridge_state", return_value=True),
            mock.patch.object(
                server,
                "run_batch_build_config_compile_matrix_probe",
                return_value={
                    "succeeded": False,
                    "batch_probe": {
                        "error": {
                            "code": "editor_running_batch_conflict",
                            "message": "Editor is already running.",
                        }
                    },
                    "top_actionable_error": "Editor is already running.",
                },
            ),
            mock.patch.object(server, "print_json", side_effect=lambda payload: emitted_payloads.append(dict(payload))),
        ):
            with self.assertRaises(SystemExit) as ctx:
                server.cmd_recover_editor_session(args)

        self.assertEqual(1, ctx.exception.code)
        self.assertEqual(1, len(emitted_payloads))
        payload = emitted_payloads[0]
        self.assertEqual("compile_probe_blocked_by_live_editor", payload["recovery_classification"])
        self.assertEqual("close_same_project_editor_or_use_interactive_lane", payload["recovery_recommended_next_action"])
        self.assertEqual(
            "xuunity_light_unity_mcp.sh request-editor-quit --project-root /tmp/FakeProject --timeout-ms 30000 --wait-for-exit --exit-timeout-ms 30000",
            payload["recommended_recovery_command"].replace('\\', '/'),
        )
        self.assertNotIn("reopen_block_reason", payload)
        self.assertFalse(bool(payload.get("reopen_blocked")))

    def test_recover_editor_session_open_editor_uses_completed_process_helper(self) -> None:
        args = argparse.Namespace(
            project_root="/tmp/FakeProject",
            timeout_ms=180000,
            close_timeout_ms=45000,
            open_editor=True,
            force_compile_probe=False,
            heartbeat_max_age_seconds=10,
            startup_policy="fail_fast_on_interactive_compile_block",
        )
        discovery = {
            "reconciliation_case": "host_launchable_not_active",
            "detected_editor_pids": [],
            "editor_log_diagnosis": {},
        }
        emitted_payloads: list[dict[str, object]] = []
        completed = mock.Mock(returncode=0, stderr="")

        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "refresh_project_context"),
            mock.patch.object(server, "build_project_discovery_report", return_value=discovery),
            mock.patch.object(server, "current_project_context_host_session_state", return_value={}),
            mock.patch.object(
                server,
                "run_self_json_command_with_completed",
                return_value=({"project_root": "/tmp/FakeProject"}, completed),
            ) as run_mock,
            mock.patch.object(server, "print_json", side_effect=lambda payload: emitted_payloads.append(dict(payload))),
        ):
            server.cmd_recover_editor_session(args)

        run_mock.assert_called_once()
        self.assertEqual(1, len(emitted_payloads))
        payload = emitted_payloads[0]
        self.assertEqual("recovered", payload["recovery_classification"])
        self.assertEqual({"project_root": "/tmp/FakeProject"}, payload["ensure_ready"])

    def test_ensure_ready_without_open_editor_fails_fast_when_project_is_offline(self) -> None:
        args = argparse.Namespace(
            project_root="/tmp/FakeProject",
            open_editor=False,
            unity_app=None,
            editor_log_path=None,
            background_open=False,
            timeout_ms=120000,
            heartbeat_max_age_seconds=10,
            startup_policy="fail_fast_on_interactive_compile_block",
        )
        discovery = {
            "reconciliation_case": "host_launchable_not_active",
            "reconciliation_status": "offline",
            "reconciliation_recommended_next_action": "open_editor_or_ensure_ready",
            "detected_editor_count": 0,
            "detected_editor_pids": [],
        }

        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "resolve_editor_log_path", return_value=Path("/tmp/editor.log")),
            mock.patch.object(server, "build_project_discovery_report", return_value=discovery),
            mock.patch.object(server, "current_project_context_bridge_state", return_value={}),
            mock.patch.object(server, "enrich_tool_invocation_error_with_discovery", side_effect=lambda _, exc: exc),
            mock.patch.object(server, "wait_for_ready") as wait_mock,
        ):
            with self.assertRaises(server.ToolInvocationError) as ctx:
                server.cmd_ensure_ready(args)

        self.assertEqual("editor_not_running", ctx.exception.code)
        self.assertEqual(
            "ensure_ready_without_open_editor_offline",
            ctx.exception.details["fail_fast_reason"],
        )
        self.assertEqual("open_editor_or_ensure_ready", ctx.exception.details["recommended_next_action"])
        self.assertEqual(
            "xuunity_light_unity_mcp.sh ensure-ready --project-root /tmp/FakeProject --open-editor",
            ctx.exception.details["recommended_recovery_command"].replace('\\', '/'),
        )
        wait_mock.assert_not_called()

    def test_ensure_ready_timeout_reports_unresolved_package_import_state(self) -> None:
        args = argparse.Namespace(
            project_root="/tmp/FakeProject",
            open_editor=True,
            unity_app=None,
            editor_log_path=None,
            background_open=False,
            timeout_ms=120000,
            heartbeat_max_age_seconds=10,
            startup_policy="fail_fast_on_interactive_compile_block",
        )
        discovery = {
            "reconciliation_case": "same_project_editor_running_bridge_not_ready",
            "reconciliation_status": "degraded",
            "detected_editor_count": 1,
            "detected_editor_pids": [2468],
        }
        import_state = {
            "package_name": "com.xuunity.light-mcp",
            "manifest_declared": True,
            "manifest_dependency": "https://example.invalid/repo.git#abc123",
            "lock_entry_present": False,
            "package_cache_present": False,
            "bridge_state_present": False,
            "import_state": "declared_not_resolved",
        }

        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "resolve_editor_log_path", return_value=Path("/tmp/editor.log")),
            mock.patch.object(server, "build_project_discovery_report", return_value=discovery),
            mock.patch.object(server, "current_project_context_bridge_state", return_value={}),
            mock.patch.object(server, "inspect_light_mcp_import_state", return_value=import_state),
            mock.patch.object(server, "detect_unity_app_path_for_project", return_value=Path("/Applications/Unity.app")),
            mock.patch.object(server, "open_unity_editor", return_value={"reused_existing_editor": True, "editor_pid": 2468}),
            mock.patch.object(server, "enrich_tool_invocation_error_with_discovery", side_effect=lambda _, exc: exc),
            mock.patch.object(
                server,
                "wait_for_ready",
                side_effect=server.ToolInvocationError("editor_ready_timeout", "Timed out"),
            ),
        ):
            with self.assertRaises(server.ToolInvocationError) as ctx:
                server.cmd_ensure_ready(args)

        self.assertEqual("editor_ready_timeout", ctx.exception.code)
        self.assertEqual(import_state, ctx.exception.details["package_import_state"])
        self.assertEqual("package_declared_not_imported", ctx.exception.details["package_import_diagnosis"])
        self.assertEqual("reopen_project_for_clean_resolve", ctx.exception.details["recommended_next_action"])
        self.assertEqual("close_and_reopen_unity_to_resolve_package", ctx.exception.details["next_distinct_action"])
        self.assertEqual([2468], ctx.exception.details["live_project_editor_pids"])

    def test_batch_editor_conflict_includes_concrete_recovery_command(self) -> None:
        project_root = Path("/tmp/FakeProject")

        with (
            mock.patch.object(server, "process_visibility_summary", return_value={
                "process_visibility_available": True,
                "process_visibility_error_code": "",
            }),
            mock.patch.object(server, "list_live_project_editor_pids", return_value=[1234]),
        ):
            with self.assertRaises(server.ToolInvocationError) as ctx:
                server.ensure_batch_project_closed(project_root, "batch compile")

        exc = ctx.exception
        self.assertEqual("editor_running_batch_conflict", exc.code)
        self.assertEqual([1234], exc.details["live_editor_pids"])
        self.assertEqual(
            "close_same_project_editor_or_use_interactive_lane",
            exc.details["recommended_next_action"],
        )
        self.assertEqual(
            "xuunity_light_unity_mcp.sh request-editor-quit --project-root /tmp/FakeProject --timeout-ms 30000 --wait-for-exit --exit-timeout-ms 30000",
            exc.details["recommended_recovery_command"].replace('\\', '/'),
        )
        self.assertFalse(exc.details["same_project_editor_closed"])
        self.assertFalse(exc.details["process_exit_verified"])
        self.assertEqual("editor_still_running", exc.details["closeout_classification"])
        self.assertTrue(exc.details["closeout_verification_required"])

        summary = server.build_batch_prepare_failure_summary(
            action="batch_compile",
            result_path=Path("/tmp/result.json"),
            log_path=Path("/tmp/editor.log"),
            exc=exc,
            truncate_text=server.truncate_text,
        )

        self.assertEqual("batch_prepare_blocked", summary["transport_outcome"])
        self.assertEqual("not_started", summary["unity_outcome"])
        self.assertEqual(exc.details["recommended_next_action"], summary["recommended_next_action"])
        self.assertEqual(exc.details["recommended_recovery_command"], summary["recommended_recovery_command"])
        self.assertTrue(summary["closeout_verification_required"])
        self.assertFalse(summary["same_project_editor_closed"])
        self.assertFalse(summary["process_exit_verified"])
        self.assertEqual("editor_still_running", summary["closeout_classification"])
        self.assertIn("process_exit_verified=true", summary["next_step"])

    def test_batch_commands_accept_timeout_ms(self) -> None:
        parser = server.build_parser()

        matrix_args = parser.parse_args(
            [
                "batch-build-config-compile-matrix",
                "--project-root",
                "/tmp/FakeProject",
                "--timeout-ms",
                "900000",
            ]
        )
        self.assertEqual(900000, matrix_args.timeout_ms)

        editmode_args = parser.parse_args(
            [
                "batch-editmode-tests",
                "--project-root",
                "/tmp/FakeProject",
                "--timeout-ms",
                "900000",
                "--dry-run",
            ]
        )
        self.assertEqual(900000, editmode_args.timeout_ms)

        quit_args = parser.parse_args(
            [
                "request-editor-quit",
                "--project-root",
                "/tmp/FakeProject",
                "--wait-for-exit",
                "--exit-timeout-ms",
                "45000",
            ]
        )
        self.assertTrue(quit_args.wait_for_exit)
        self.assertEqual(45000, quit_args.exit_timeout_ms)

        restore_args = parser.parse_args(
            [
                "restore-editor-state",
                "--project-root",
                "/tmp/FakeProject",
                "--require-closed",
            ]
        )
        self.assertTrue(restore_args.require_closed)

        verify_args = parser.parse_args(
            [
                "verify-editor-closed",
                "--project-root",
                "/tmp/FakeProject",
                "--timeout-ms",
                "12000",
            ]
        )
        self.assertEqual(12000, verify_args.timeout_ms)

        setup_args = parser.parse_args(
            [
                "setup-plan",
                "--workspace-root",
                "/tmp/Workspace",
                "--project-root",
                "/tmp/FakeProject",
                "--recursive",
                "--include-test-framework",
                "yes",
            ]
        )
        self.assertEqual("/tmp/Workspace", setup_args.workspace_root)
        self.assertEqual(["/tmp/FakeProject"], setup_args.project_root)
        self.assertTrue(setup_args.recursive)
        self.assertEqual("yes", setup_args.include_test_framework)

        request_install_args = parser.parse_args(
            [
                "request-install-test-framework",
                "--project-root",
                "/tmp/FakeProject",
                "--yes",
                "--version",
                "1.5.1",
                "--timeout-ms",
                "300000",
            ]
        )
        self.assertTrue(request_install_args.yes)
        self.assertEqual("1.5.1", request_install_args.version)
        self.assertEqual(300000, request_install_args.timeout_ms)

    def test_verify_editor_closed_success_emits_closed_payload(self) -> None:
        args = argparse.Namespace(project_root="/tmp/FakeProject", timeout_ms=30000)
        emitted_payloads: list[dict[str, object]] = []
        closed_payload = {
            "same_project_editor_closed": True,
            "live_project_editor_pids": [],
            "process_visibility_available": True,
            "process_visibility_error_code": "",
            "process_exit_verified": True,
        }

        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "verify_project_editor_closed", return_value=closed_payload),
            mock.patch.object(server, "print_json", side_effect=lambda payload: emitted_payloads.append(dict(payload))),
        ):
            server.cmd_verify_editor_closed(args)

        self.assertEqual([closed_payload], emitted_payloads)

    def test_verify_editor_closed_fails_when_process_is_live(self) -> None:
        args = argparse.Namespace(project_root="/tmp/FakeProject", timeout_ms=30000)
        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(
                server,
                "verify_project_editor_closed",
                return_value={
                    "same_project_editor_closed": False,
                    "live_project_editor_pids": [1234],
                    "process_visibility_available": True,
                    "process_visibility_error_code": "",
                    "process_exit_verified": False,
                    "closeout_classification": "editor_still_running",
                },
            ),
        ):
            with self.assertRaises(server.ToolInvocationError) as ctx:
                server.cmd_verify_editor_closed(args)

        self.assertEqual("editor_still_running", ctx.exception.code)
        self.assertEqual([1234], ctx.exception.details["live_project_editor_pids"])

    def test_request_editor_quit_wait_succeeds_when_process_exits(self) -> None:
        args = argparse.Namespace(
            project_root="/tmp/FakeProject",
            timeout_ms=15000,
            wait_for_exit=True,
            exit_timeout_ms=30000,
        )
        emitted_payloads: list[dict[str, object]] = []

        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "request_editor_quit", return_value={"status": "ok", "request_id": "quit-1"}),
            mock.patch.object(
                server,
                "verify_project_editor_closed",
                return_value={
                    "same_project_editor_closed": True,
                    "live_project_editor_pids": [],
                    "process_visibility_available": True,
                    "process_visibility_error_code": "",
                    "process_exit_verified": True,
                    "closeout_classification": "same_project_editor_closed",
                },
            ),
            mock.patch.object(server, "print_json", side_effect=lambda payload: emitted_payloads.append(dict(payload))),
        ):
            server.cmd_request_editor_quit(args)

        self.assertEqual(1, len(emitted_payloads))
        payload = emitted_payloads[0]
        self.assertTrue(payload["quit_request_accepted"])
        self.assertTrue(payload["same_project_editor_closed"])
        self.assertTrue(payload["process_exit_verified"])
        self.assertEqual("quit_ack_and_process_exit_verified", payload["closeout_classification"])

    def test_request_editor_quit_wait_fails_when_ack_does_not_exit(self) -> None:
        args = argparse.Namespace(
            project_root="/tmp/FakeProject",
            timeout_ms=15000,
            wait_for_exit=True,
            exit_timeout_ms=30000,
        )

        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "request_editor_quit", return_value={"status": "ok", "request_id": "quit-1"}),
            mock.patch.object(
                server,
                "verify_project_editor_closed",
                return_value={
                    "same_project_editor_closed": False,
                    "live_project_editor_pids": [1234],
                    "process_visibility_available": True,
                    "process_visibility_error_code": "",
                    "process_exit_verified": False,
                    "closeout_classification": "editor_still_running",
                },
            ),
        ):
            with self.assertRaises(server.ToolInvocationError) as ctx:
                server.cmd_request_editor_quit(args)

        self.assertEqual("editor_quit_ack_without_exit", ctx.exception.code)
        self.assertTrue(ctx.exception.details["quit_request_accepted"])
        self.assertEqual([1234], ctx.exception.details["live_project_editor_pids"])
        self.assertEqual("editor_quit_ack_without_exit", ctx.exception.details["closeout_classification"])

    def test_restore_editor_state_require_closed_fails_when_project_still_live(self) -> None:
        args = argparse.Namespace(project_root="/tmp/FakeProject", timeout_ms=15000, require_closed=True)
        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(
                server,
                "restore_host_opened_editor_state",
                return_value={
                    "host_opened_session_found": False,
                    "closeout_verified": True,
                    "same_project_editor_closed": False,
                    "live_project_editor_pids": [1234],
                    "process_visibility_available": True,
                    "process_exit_verified": False,
                },
            ),
            mock.patch.object(server, "refresh_project_context"),
            mock.patch.object(server, "build_project_discovery_report", return_value={}),
        ):
            with self.assertRaises(server.ToolInvocationError) as ctx:
                server.cmd_restore_editor_state(args)

        self.assertEqual("restore_editor_state_incomplete", ctx.exception.code)
        self.assertEqual([1234], ctx.exception.details["live_project_editor_pids"])

    def test_test_framework_regression_defaults_are_public_safe(self) -> None:
        parser = server.build_parser()
        args = parser.parse_args(
            [
                "batch-test-framework-version-regression",
                "--project-root",
                "/tmp/FakeProject",
            ]
        )

        self.assertEqual("active", args.compile_target)
        self.assertEqual([], args.focus_assembly_name)
        self.assertEqual([], args.focus_test_name)
        self.assertFalse(args.no_generated_focus_test)

    def test_generated_test_framework_focus_fixture_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            (project_root / "Assets").mkdir()

            fixture = server.deploy_test_framework_regression_focus_fixture(
                project_root,
                server.TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_RELATIVE_DIR,
            )

            fixture_path = Path(fixture["fixture_path"])
            self.assertTrue(fixture_path.is_file())
            self.assertIn(
                server.TEST_FRAMEWORK_REGRESSION_GENERATED_FOCUS_TEST_NAME,
                fixture["test_name"],
            )

            cleanup = server.cleanup_test_framework_regression_focus_fixture(fixture)

            self.assertTrue(cleanup["removed_file"])
            self.assertFalse(fixture_path.exists())

    def test_error_summary_includes_closeout_verified_false(self) -> None:
        payload = {
            "error": {"code": "restore_editor_state_incomplete", "message": "closeout incomplete"},
            "closeout_classification": "quit_ack_without_exit",
            "closeout_verified": False,
            "process_visibility_error_code": "none",
            "same_project_editor_closed": False,
            "process_exit_verified": False,
            "next_distinct_action": "manual_editor_close",
            "recommended_next_action": "manual_editor_close",
            "recommended_recovery_command": "xuunity_light_unity_mcp.sh recover-editor-session --project-root /tmp/FakeProject",
        }

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            server.emit_tool_error_summary(payload)

        output = stderr.getvalue()
        self.assertIn("closeout_classification=quit_ack_without_exit", output)
        self.assertIn("closeout_verified=false", output)
        self.assertIn("same_project_editor_closed=false", output)
        self.assertIn("process_exit_verified=false", output)
        self.assertIn("next_distinct_action=manual_editor_close", output)
        self.assertIn("recovery_command xuunity_light_unity_mcp.sh recover-editor-session", output)

    def test_request_playmode_tests_exits_playmode_and_retries_once(self) -> None:
        args = argparse.Namespace(
            project_root="/tmp/FakeProject",
            timeout_ms=None,
            test_names=None,
            group_names=None,
            category_names=None,
            assembly_names=None,
        )
        emitted_payloads: list[dict[str, object]] = []
        invoke_calls: list[tuple[str, dict[str, object], int]] = []

        def fake_invoke_bridge(
            project_root_value: str,
            operation: str,
            operation_args: dict[str, object],
            timeout_ms: int,
        ) -> dict[str, object]:
            invoke_calls.append((operation, dict(operation_args), timeout_ms))
            if operation == "unity.tests.run_playmode" and len([call for call in invoke_calls if call[0] == operation]) == 1:
                return {
                    "status": "ok",
                    "payload_json": (
                        '{"status":"error","error":{"code":"playmode_state_invalid",'
                        '"message":"Cannot run PlayMode tests unless Unity is in edit mode. Current state: playing."}}'
                    ),
                }
            if operation == "unity.playmode.set":
                return {
                    "status": "ok",
                    "payload_json": '{"status":"ok","state":"edit"}',
                }
            return {
                "status": "ok",
                "payload_json": '{"status":"ok","total":47,"passed":47}',
            }

        def fake_timeout(project_root: Path, operation: str, fallback_timeout_ms: int) -> int:
            if operation == "unity.tests.run_playmode":
                return 300000
            if operation == "unity.playmode.set":
                return 180000
            raise AssertionError(f"Unexpected operation: {operation}")

        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "invoke_bridge", side_effect=fake_invoke_bridge),
            mock.patch.object(server, "resolve_operation_default_timeout_ms", side_effect=fake_timeout),
            mock.patch.object(server, "print_json", side_effect=lambda payload: emitted_payloads.append(dict(payload))),
        ):
            server.cmd_request_playmode_tests(args)

        self.assertEqual(1, len(emitted_payloads))
        self.assertEqual("ok", emitted_payloads[0]["status"])
        self.assertEqual(
            [
                ("unity.tests.run_playmode", {"testNames": None, "groupNames": None, "categoryNames": None, "assemblyNames": None}, 300000),
                ("unity.playmode.set", {"action": "exit"}, 180000),
                ("unity.tests.run_playmode", {"testNames": None, "groupNames": None, "categoryNames": None, "assemblyNames": None}, 300000),
            ],
            invoke_calls,
        )

    def test_request_playmode_tests_retries_when_bridge_returns_top_level_playmode_error(self) -> None:
        args = argparse.Namespace(
            project_root="/tmp/FakeProject",
            timeout_ms=None,
            test_names=None,
            group_names=None,
            category_names=None,
            assembly_names=None,
        )
        emitted_payloads: list[dict[str, object]] = []
        invoke_calls: list[tuple[str, dict[str, object], int]] = []

        def fake_invoke_bridge(
            project_root_value: str,
            operation: str,
            operation_args: dict[str, object],
            timeout_ms: int,
        ) -> dict[str, object]:
            invoke_calls.append((operation, dict(operation_args), timeout_ms))
            if operation == "unity.tests.run_playmode" and len([call for call in invoke_calls if call[0] == operation]) == 1:
                return {
                    "request_id": "play-1",
                    "status": "error",
                    "completed_at_utc": "2026-05-11T22:40:59Z",
                    "payload_type": "",
                    "payload_json": "",
                    "error": {
                        "code": "playmode_state_invalid",
                        "message": "Cannot run PlayMode tests unless Unity is in edit mode. Current state: playing.",
                    },
                }
            if operation == "unity.playmode.set":
                return {
                    "status": "ok",
                    "payload_json": '{"status":"ok","state":"edit"}',
                }
            return {
                "status": "ok",
                "payload_json": '{"status":"passed","total":47,"passed":47}',
            }

        def fake_timeout(project_root: Path, operation: str, fallback_timeout_ms: int) -> int:
            if operation == "unity.tests.run_playmode":
                return 300000
            if operation == "unity.playmode.set":
                return 180000
            raise AssertionError(f"Unexpected operation: {operation}")

        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "invoke_bridge", side_effect=fake_invoke_bridge),
            mock.patch.object(server, "resolve_operation_default_timeout_ms", side_effect=fake_timeout),
            mock.patch.object(server, "print_json", side_effect=lambda payload: emitted_payloads.append(dict(payload))),
        ):
            server.cmd_request_playmode_tests(args)

        self.assertEqual(1, len(emitted_payloads))
        self.assertEqual("ok", emitted_payloads[0]["status"])
        self.assertEqual(3, len(invoke_calls))
        self.assertEqual("unity.tests.run_playmode", invoke_calls[0][0])
        self.assertEqual("unity.playmode.set", invoke_calls[1][0])
        self.assertEqual("unity.tests.run_playmode", invoke_calls[2][0])

    def test_initialize_returns_protocol_version(self) -> None:
        response = server.handle_json_rpc_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
            {"initialized": False, "protocolVersion": None},
        )

        self.assertEqual(server.PROTOCOL_VERSION, response["result"]["protocolVersion"])
        self.assertEqual("xuunity-mcp", response["result"]["serverInfo"]["name"])


if __name__ == "__main__":
    unittest.main()
