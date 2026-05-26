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
import server_license


class LicenseCapabilitiesTests(unittest.TestCase):
    def test_license_log_classification_uses_stable_blocker_codes(self) -> None:
        samples = {
            "No valid Unity Editor license found. Please activate your license.": "no_valid_editor_license",
            "Access token is unavailable; cannot continue batchmode activation.": "access_token_unavailable",
            "No ULF license found in expected location.": "no_ulf_license",
            "Build Server license does not have the Editor UI entitlement.": "headless_entitlement_missing",
            "Licensing Client IPC connection failed.": "licensing_client_ipc_failure",
        }

        for text, expected_code in samples.items():
            with self.subTest(expected_code=expected_code):
                result = server_license.classify_license_log(text, exit_code=1)
                self.assertEqual(expected_code, result["batchmode_blocker_code"])

    def test_batch_lane_preflight_auto_selects_gui_for_known_license_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            payload = {"action": "batch_compile_player_scripts"}
            with (
                mock.patch.object(server, "process_visibility_summary", return_value={"process_visibility_available": True}),
                mock.patch.object(server, "list_live_project_editor_pids", return_value=[]),
                mock.patch.object(
                    server,
                    "build_license_capabilities",
                    return_value={
                        "batchmode_supported": False,
                        "editor_ui_supported": None,
                        "batchmode_blocker_code": "access_token_unavailable",
                        "batchmode_probe_log_path": str(project_root / "probe.log"),
                        "recommended_execution_lane": "gui",
                    },
                ),
            ):
                lane, capabilities = server.batch_lane_preflight_blocker(
                    project_root=project_root,
                    unity_app=Path("/Applications/FakeUnity.app"),
                    batch_fallback_mode="auto",
                    payload=payload,
                    action_label="batch compile",
                    timeout_ms=30000,
                )

            self.assertEqual("gui", lane)
            self.assertEqual("access_token_unavailable", payload["lane_fallback_reason"])
            self.assertFalse(payload["license_batchmode_supported"])
            self.assertEqual("access_token_unavailable", capabilities["batchmode_blocker_code"])

    def test_batch_lane_preflight_require_batch_fails_when_not_proven(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            with (
                mock.patch.object(server, "process_visibility_summary", return_value={"process_visibility_available": True}),
                mock.patch.object(server, "list_live_project_editor_pids", return_value=[]),
                mock.patch.object(
                    server,
                    "build_license_capabilities",
                    return_value={
                        "batchmode_supported": None,
                        "editor_ui_supported": None,
                        "batchmode_blocker_code": "unknown_batch_failure",
                        "batchmode_probe_log_path": str(project_root / "probe.log"),
                        "recommended_execution_lane": "batch_diagnostic_required",
                    },
                ),
            ):
                with self.assertRaises(server.ToolInvocationError) as raised:
                    server.batch_lane_preflight_blocker(
                        project_root=project_root,
                        unity_app=Path("/Applications/FakeUnity.app"),
                        batch_fallback_mode="require-batch",
                        payload={"action": "batch_compile_player_scripts"},
                        action_label="batch compile",
                        timeout_ms=30000,
                    )

            self.assertEqual("batchmode_not_supported", raised.exception.code)
            self.assertEqual("require-batch", raised.exception.details["batch_fallback_mode"])

    def test_run_batch_operation_uses_gui_fallback_when_auto_preflight_selects_gui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            payload = {"action": "batch_compile_player_scripts"}
            with (
                mock.patch.object(server, "process_visibility_summary", return_value={"process_visibility_available": True}),
                mock.patch.object(server, "list_live_project_editor_pids", return_value=[]),
                mock.patch.object(
                    server,
                    "build_license_capabilities",
                    return_value={
                        "batchmode_supported": False,
                        "editor_ui_supported": None,
                        "batchmode_blocker_code": "no_valid_editor_license",
                        "batchmode_probe_log_path": str(project_root / "probe.log"),
                        "recommended_execution_lane": "gui",
                    },
                ),
                mock.patch.object(server, "run_gui_fallback_operation") as gui_fallback,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                server.run_batch_operation(
                    project_root=project_root,
                    unity_app=Path("/Applications/FakeUnity.app"),
                    command=["/bin/false"],
                    payload=payload,
                    log_path=project_root / "batch.log",
                    result_path=project_root / "result.json",
                    dry_run=False,
                    timeout_ms=30000,
                    progress_stdout=False,
                    batch_fallback_mode="auto",
                    gui_operation="unity.compile.player_scripts",
                    gui_operation_args={"target": "Android"},
                )

            gui_fallback.assert_called_once()
            self.assertEqual("gui", payload["effective_execution_lane"])
            self.assertEqual("no_valid_editor_license", payload["lane_fallback_reason"])

    def test_build_license_capabilities_cache_records_probe_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            unity_app = Path(tmp_dir) / "Unity.app"
            unity_binary = Path(tmp_dir) / "Unity"
            completed = mock.Mock(returncode=0, stdout="", stderr="")
            with (
                mock.patch.object(server_license, "detect_unity_app_path_for_project", return_value=unity_app),
                mock.patch.object(server_license, "resolve_unity_executable", return_value=unity_binary),
                mock.patch.object(server_license, "resolve_unity_app_version", return_value="2022.3.67f2"),
                mock.patch.object(server_license.subprocess, "run", return_value=completed) as run_probe,
            ):
                first = server_license.build_license_capabilities(project_root=project_root, refresh=True)
                second = server_license.build_license_capabilities(project_root=project_root, refresh=False)

            self.assertTrue(first["batchmode_supported"])
            self.assertEqual("batch", first["recommended_execution_lane"])
            self.assertTrue(second["from_cache"])
            self.assertEqual("2022.3.67f2", second["unity_version"])
            self.assertEqual(1, run_probe.call_count)

    def test_mcp_license_capabilities_tool_returns_structured_content(self) -> None:
        payload = {"action": "license_capabilities", "batchmode_supported": True}
        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "detect_unity_app_path_for_project", return_value=Path("/tmp/Unity.app")),
            mock.patch.object(server, "build_license_capabilities", return_value=payload),
        ):
            result = server.call_xuunity_license_capabilities_tool(
                {"projectRoot": "/tmp/FakeProject", "timeoutMs": 1000}
            )

        self.assertFalse(result["isError"])
        self.assertEqual(payload, result["structuredContent"])
        self.assertEqual(payload, json.loads(result["content"][0]["text"]))


if __name__ == "__main__":
    unittest.main()
