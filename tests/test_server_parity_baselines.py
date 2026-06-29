import argparse
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server
import server_batch_reporting
import server_bridge_runtime
import server_core
import server_mcp_tools
import server_specs
import server_summaries


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "server_parity_baseline.json"


def load_baseline() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def get_subparser(parser: argparse.ArgumentParser, command: str) -> argparse.ArgumentParser:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[command]
    raise AssertionError(f"Parser has no subcommands; expected {command}.")


def get_root_subcommands(parser: argparse.ArgumentParser) -> list[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return list(action.choices)
    raise AssertionError("Parser has no subcommands.")


def get_option_groups(parser: argparse.ArgumentParser) -> list[list[str]]:
    return [list(action.option_strings) for action in parser._actions if action.option_strings]


def fake_bridge_response_to_tool_result(response: dict, **kwargs) -> dict:
    payload = {"bridge_response": response}
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=True)}],
        "structuredContent": payload,
        "isError": False,
    }


def fake_tool_error_payload(exc: server_core.ToolInvocationError) -> dict:
    payload = {"error": {"code": exc.code, "message": exc.message}}
    if exc.details:
        payload["error"]["details"] = dict(exc.details)
    return payload


class ServerParityBaselineTests(unittest.TestCase):
    maxDiff = None

    def test_cli_help_baseline_matches_fixture(self) -> None:
        expected = load_baseline()["cli_help"]
        with mock.patch.dict(os.environ, {"COLUMNS": "80"}), mock.patch.object(sys, "argv", ["server.py"]):
            parser = server.build_parser()
            root_help = parser.format_help()
            root_commands = get_root_subcommands(parser)
            status_parser = get_subparser(parser, "request-status-summary")
            scenario_parser = get_subparser(parser, "request-scenario-run-and-wait")

        for needle in expected["root_contains"]:
            self.assertIn(needle, root_help)
        self.assertIn("XUUnity Light Unity MCP server.", root_help)
        self.assertEqual(expected["root_command_count"], len(root_commands))
        self.assertEqual(expected["root_commands"], root_commands)
        self.assertEqual(expected["request_status_summary_options"], get_option_groups(status_parser))
        self.assertEqual(expected["request_scenario_run_and_wait_options"], get_option_groups(scenario_parser))

    def test_mcp_tool_list_json_baseline_matches_fixture(self) -> None:
        expected = load_baseline()["mcp_tools_list"]
        response = server.handle_json_rpc_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            {"initialized": True, "protocolVersion": server.PROTOCOL_VERSION},
        )
        tool_names = [tool["name"] for tool in response["result"]["tools"]]

        self.assertEqual(expected["tool_count"], len(tool_names))
        self.assertEqual(expected["tool_names"], tool_names)
        self.assertEqual(expected["sha256"], sha256_text(canonical_json(response)))

    def test_representative_call_tool_success_matches_fixture(self) -> None:
        actual = server_mcp_tools.call_tool(
            "unity_scene_snapshot",
            {"projectRoot": "ParityProject", "timeoutMs": 1234, "includeInactive": True},
            tools=server_specs.TOOLS,
            special_tool_handlers={},
            tool_invocation_error_type=server_core.ToolInvocationError,
            ensure_project_root=lambda value: Path(value),
            resolve_operation_timeout_ms=lambda project_root, operation, value, default: int(value or default),
            invoke_bridge=lambda root, operation, bridge_args, timeout_ms: {
                "root": root,
                "operation": operation,
                "args": bridge_args,
                "timeout_ms": timeout_ms,
            },
            build_tool_error_payload=fake_tool_error_payload,
            bridge_response_to_tool_result=fake_bridge_response_to_tool_result,
        )

        self.assertEqual(load_baseline()["call_tool_success"], actual)

    def test_representative_call_tool_error_matches_fixture(self) -> None:
        def raise_bridge(*args, **kwargs):
            raise server_core.ToolInvocationError(
                "bridge_unavailable",
                "Bridge unavailable for parity fixture.",
                {"project_root": args[0] if args else ""},
            )

        actual = server_mcp_tools.call_tool(
            "unity_scene_snapshot",
            {"projectRoot": "ParityProject", "timeoutMs": 1234},
            tools=server_specs.TOOLS,
            special_tool_handlers={},
            tool_invocation_error_type=server_core.ToolInvocationError,
            ensure_project_root=lambda value: Path(value),
            resolve_operation_timeout_ms=lambda project_root, operation, value, default: int(value or default),
            invoke_bridge=raise_bridge,
            build_tool_error_payload=fake_tool_error_payload,
            bridge_response_to_tool_result=fake_bridge_response_to_tool_result,
        )

        self.assertEqual(load_baseline()["call_tool_error"], actual)

    def test_bridge_stabilization_summary_matches_fixture(self) -> None:
        actual = server_bridge_runtime.build_bridge_stabilization_summary(
            {
                "bridge_generation": 12,
                "bridge_session_id": "session-parity",
                "transport": "tcp_loopback",
                "transport_listener_state": "closed",
                "health_status": "unstable",
                "pending_request_count": 2,
                "domain_reload_in_progress": True,
                "compile_settle_pending": True,
            },
            editor_running=False,
            mcp_reachable=False,
        )

        self.assertEqual(load_baseline()["bridge_stabilization_summary"], actual)

    def test_request_final_status_projection_matches_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            journal_dir = project_root / "Library" / "XUUnityLightMcp" / "journal" / "requests"
            journal_dir.mkdir(parents=True)
            request_id = "req-parity"
            write_json(
                journal_dir / "01_request_submitted.json",
                {
                    "event_id": "01",
                    "event_type": "request_submitted",
                    "event_at_utc": "2026-06-25T10:00:00Z",
                    "request_id": request_id,
                    "operation": "unity.project.refresh",
                    "bridge_generation": 1,
                    "bridge_session_id": "session-old",
                },
            )

            summary = server_bridge_runtime.build_request_final_status(
                project_root,
                request_id,
                "unity.project.refresh",
                current_state={
                    "bridge_generation": 2,
                    "bridge_session_id": "session-new",
                    "transport": "tcp_loopback",
                    "transport_listener_state": "listening",
                    "health_status": "healthy",
                    "pending_request_count": 0,
                },
                poll_timeout_ms=0,
            )

        actual = {
            key: summary.get(key)
            for key in [
                "request_submitted",
                "request_started",
                "request_completed",
                "request_observed_in_unity_journal",
                "bridge_changed_since_submission",
                "recovery_gap_detected",
                "operation_outcome",
                "result_trust_class",
                "recommended_next_action",
                "journal_event_count",
            ]
        }
        actual["operator_verdict"] = summary.get("operator_verdict")

        self.assertEqual(load_baseline()["request_final_status_projection"], actual)

    def test_batch_prepare_failure_summary_matches_fixture(self) -> None:
        class FakeError:
            code = "batch_preflight_blocked"
            message = "Unity editor is already open.\nClose it before running batch compile."
            details = {
                "recommended_next_action": "close_editor_then_retry",
                "same_project_editor_closed": False,
                "process_visibility_available": True,
            }

        actual = server_batch_reporting.build_batch_prepare_failure_summary(
            action="batch-compile",
            result_path=Path("result.json"),
            log_path=Path("unity.log"),
            exc=FakeError(),
            truncate_text=server_summaries.truncate_text,
        )

        self.assertEqual(load_baseline()["batch_prepare_failure_summary"], actual)

    def test_scenario_result_summary_matches_fixture(self) -> None:
        actual = server_summaries.build_scenario_result_summary(
            {
                "project_root": "ParityProject",
                "run_id": "run-parity",
                "scenario_name": "scenario_parity",
                "status": "failed",
                "terminal": True,
                "succeeded": False,
                "terminal_status": "failed",
                "started_at_utc": "2026-06-25T10:00:00Z",
                "updated_at_utc": "2026-06-25T10:00:05Z",
                "completed_at_utc": "2026-06-25T10:00:05Z",
                "duration_seconds": 5.4321,
                "total_steps": 2,
                "passed_steps": 1,
                "failed_steps": 1,
                "skipped_steps": 0,
                "current_step_index": 1,
                "result_path": "scenario-result.json",
                "steps": [
                    {"stepId": "open", "kind": "scene_snapshot", "status": "passed", "duration_seconds": 1.2},
                    {
                        "stepId": "assert",
                        "kind": "assert_scene",
                        "status": "failed",
                        "error_code": "missing_root",
                        "error_message": "Root object missing.",
                        "duration_seconds": 0.5,
                    },
                ],
            },
            server_specs.SCENARIO_TERMINAL_STATUSES,
        )

        self.assertEqual(load_baseline()["scenario_result_summary"], actual)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
