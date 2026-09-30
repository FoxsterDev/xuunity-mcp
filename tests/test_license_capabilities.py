import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server
import server_batch_reporting
import server_core
import server_license
import server_licensing_state
import server_summary_status
import server_hub_licensing
import server_editor_host_lifecycle
import server_editor_host


def hold_licensing_lock_in_child(directory, ready, release):
    server_licensing_state.licensing_host_state_dir = lambda: Path(directory)
    with server_licensing_state.licensing_host_lock():
        ready.set()
        release.wait(10)


class LicensingHostStatePathTests(unittest.TestCase):
    def test_host_state_path_survives_missing_home_resolution(self):
        with (
            mock.patch.object(server_licensing_state.Path, "home", side_effect=RuntimeError("no home")),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            path = server_licensing_state.licensing_host_state_dir()
        self.assertTrue(path.name.startswith("xuunity-licensing-"))
        self.assertEqual(20, len(path.name.removeprefix("xuunity-licensing-")))


class LicenseCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        state_path = Path(directory.name) / "host"
        for module in (server_license, server_licensing_state):
            patcher = mock.patch.object(module, "licensing_host_state_dir", return_value=state_path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_lock_is_shared_with_an_independent_helper_process(self):
        context = multiprocessing.get_context("spawn")
        ready, release = context.Event(), context.Event()
        child = context.Process(target=hold_licensing_lock_in_child, args=(str(server_licensing_state.licensing_host_state_dir()), ready, release))
        child.start()
        try:
            self.assertTrue(ready.wait(8))
            self.assertTrue(server_licensing_state.license_probe_active())
            with self.assertRaises(server_core.ToolInvocationError) as raised:
                with server_licensing_state.licensing_host_lock(0):
                    self.fail("Concurrent helper acquired the same host lock")
            self.assertEqual("licensing_busy", raised.exception.code)
        finally:
            release.set()
            child.join(10)
        self.assertEqual(0, child.exitcode)
        self.assertFalse(server_licensing_state.license_probe_active())

    def test_concurrent_probes_and_twelve_project_sweep_launch_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            started, release = threading.Event(), threading.Event()
            def probe(*args, **kwargs):
                started.set()
                self.assertTrue(release.wait(5))
                return mock.Mock(returncode=0, stdout="", stderr="")
            with (
                mock.patch.object(server_license, "detect_unity_app_path_for_project", return_value=root / "Unity.app"),
                mock.patch.object(server_license, "resolve_unity_executable", return_value=root / "Unity"),
                mock.patch.object(server_license, "resolve_unity_app_version", return_value="6000.0.58f2"),
                mock.patch.object(server_license, "live_editor_licensing_evidence", return_value={}),
                mock.patch.object(server_license.subprocess, "run", side_effect=probe) as run,
                ThreadPoolExecutor(max_workers=2) as executor,
            ):
                first = executor.submit(server_license.build_license_capabilities, project_root=root / "0")
                self.assertTrue(started.wait(5))
                self.assertTrue(server_licensing_state.license_probe_active())
                second = executor.submit(server_license.build_license_capabilities, project_root=root / "1")
                release.set()
                results = [first.result(5), second.result(5)]
                results += [server_license.build_license_capabilities(project_root=root / str(i)) for i in range(2, 12)]
                self.assertEqual(1, run.call_count)
                self.assertEqual(11, sum(bool(item["from_cache"]) for item in results))
                self.assertEqual("host_probe_cache", results[1]["probe_skipped_reason"])
                self.assertEqual(str(root / "11"), results[-1]["project_root"])
                self.assertFalse(server_licensing_state.license_probe_active())

    def test_licensed_editor_skips_probe_without_claiming_batch_support(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(server_license, "detect_unity_app_path_for_project", return_value=Path(tmp)),
            mock.patch.object(server_license, "resolve_unity_executable", return_value=Path(tmp) / "Unity"),
            mock.patch.object(server_license, "resolve_unity_app_version", return_value="6000.0.58f2"),
            mock.patch.object(server_license, "live_editor_licensing_evidence", return_value={
                "licensed_editor_live": True, "resolution": {"status": "resolved"}}),
            mock.patch.object(server_license.subprocess, "run") as run,
        ):
            result = server_license.build_license_capabilities(project_root=Path(tmp))
        run.assert_not_called()
        self.assertEqual("licensed_editor_live", result["probe_skipped_reason"])
        self.assertIsNone(result["batchmode_supported"])
        self.assertEqual("gui", result["recommended_execution_lane"])

    def test_probe_lock_releases_after_exception_and_gui_refuses_fast(self):
        with server_licensing_state.licensing_host_lock():
            with self.assertRaises(server_core.ToolInvocationError) as raised:
                server_editor_host.open_unity_editor(Path("/tmp/P"), Path("/tmp/P/log"), Path("/tmp/Unity"), False)
            self.assertEqual("licensing_busy", raised.exception.code)
        with self.assertRaises(RuntimeError):
            with server_licensing_state.licensing_host_lock():
                raise RuntimeError("test")
        self.assertFalse(server_licensing_state.license_probe_active())

    def test_status_refuses_unlicensed_healthy_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "Editor.log"
            log.write_text("The following packages were not registered because your license doesn't allow it", encoding="utf-8")
            result = server_summary_status.build_status_summary(
                Path(tmp), {"editor_pid": 42, "health_status": "healthy", "editor_log_path": str(log)},
                read_best_effort_bridge_state=lambda _: {}, try_read_bridge_state=lambda _: {},
                pid_is_alive=lambda _: True, heartbeat_age_seconds=lambda _: 0,
                derive_busy_reason=lambda _: "", summarize_state_for_error=lambda _: "healthy",
            )
        self.assertEqual("unlicensed", result["license_state"])
        self.assertEqual("unlicensed", result["health_status"])
        self.assertIn("unlicensed", result["blocking_reasons"])
        self.assertFalse(result["transport_ready_for_requests"])
        self.assertIn("open-editor", result["recommended_next_action"])

    def test_external_licensing_timeout_explains_missing_forwarding(self):
        with mock.patch.object(server_editor_host_lifecycle, "resolve_hub_licensing_ipc", return_value=({"status": "resolved"}, "")):
            error = server_editor_host_lifecycle._launch_blocked_error({
                "startup_blocker_kind": "licensing_initialization_failed", "opened_by_host": False})
        self.assertEqual("licensing_ipc_not_forwarded_external_launch", error.details["licensing_handoff_classification"])
        self.assertIn("open-editor", error.details["recommended_next_action"])

    def test_connection_loss_overrides_earlier_entitlement_until_recovery(self):
        success = "[Licensing::Client] Successfully resolved entitlement details\n"
        lost = "[Licensing::Module] Error: The connection with the Unity Licensing Client has been lost. Attempting to reconnect.\n"
        self.assertEqual("unlicensed", server_licensing_state.license_state_from_log(success + lost))
        self.assertEqual("licensed", server_licensing_state.license_state_from_log(success + lost + success))
        kinds = [kind for kind, pattern in server_editor_host_lifecycle.STARTUP_BLOCKER_PATTERNS if pattern.search(lost)]
        self.assertIn("licensing_connection_lost", kinds)
        result = server_license.classify_license_log(lost, exit_code=1)
        self.assertEqual("licensing_client_ipc_failure", result["batchmode_blocker_code"])

    def test_licensing_error_counts_require_later_entitlement(self):
        chatter = "LicensingClient has failed validation; ignoring\nAccess token is unavailable\n"
        for suffix, expected in [("", 2), ("Successfully resolved entitlement details", 0)]:
            result = server_batch_reporting.classify_build_error_counts(2, chatter + suffix)
            self.assertEqual(expected, result["build_errors"])
            self.assertEqual(2, result["total_errors"])
        result = server_batch_reporting.classify_build_error_counts(3, chatter + "Successfully resolved entitlement details\nAccess token is unavailable")
        self.assertEqual(1, result["build_errors"])
        self.assertEqual(2, result["startup_errors"])

    def test_build_summary_splits_errors_from_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "build.log"
            log.write_text("Access token is unavailable\nSuccessfully resolved entitlement details", encoding="utf-8")
            result = server_batch_reporting.build_batch_execution_summary(
                action="plain_batch_build", result_payload={"total_errors": 1, "build_result": "Succeeded"},
                batch_exit_code=0, succeeded=True, result_path=Path(tmp) / "result.json", log_path=log,
                log_excerpt_hint="", truncate_text=lambda value, limit: str(value)[:limit])
        self.assertEqual(0, result["build_errors"])
        self.assertEqual(1, result["startup_errors"])


    def test_incremental_log_evidence_preserves_partial_lines_and_resets_on_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Editor.log"
            path.write_text("Access token is unavailable", encoding="utf-8")
            self.assertEqual("unlicensed", server_licensing_state.license_state_from_log(server_licensing_state.read_license_log(path)))
            self.assertEqual("unlicensed", server_licensing_state.license_state_from_log(server_licensing_state.read_license_log(path)))
            with path.open("a", encoding="utf-8") as stream:
                stream.write("\nSuccessfully resolved entitlement details\n")
            text = server_licensing_state.read_license_log(path)
            self.assertEqual(1, text.count("Access token is unavailable"))
            self.assertEqual("licensed", server_licensing_state.license_state_from_log(text))
            path.write_text("No valid Unity Editor license found\n", encoding="utf-8")
            self.assertEqual("unlicensed", server_licensing_state.license_state_from_log(server_licensing_state.read_license_log(path)))

    def test_live_gui_proof_selects_gui_lane_even_when_batch_entitlement_unknown(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(server, "process_visibility_summary", return_value={"process_visibility_available": True}),
            mock.patch.object(server, "list_live_project_editor_pids", return_value=[]),
            mock.patch.object(server, "build_license_capabilities", return_value={
                "batchmode_supported": None, "probe_skipped_reason": "licensed_editor_live"}),
        ):
            lane, _ = server.batch_lane_preflight_blocker(
                project_root=Path(tmp), unity_app=Path(tmp) / "Unity", batch_fallback_mode="auto",
                payload={}, action_label="test", timeout_ms=1000)
        self.assertEqual("gui", lane)

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

    def test_license_log_classification_ignores_recovered_access_token_warning(self) -> None:
        text = "\n".join(
            [
                "[Licensing::Module] Error: Access token is unavailable; failed to update",
                "[Licensing::Client] Successfully resolved entitlement details",
                "[Licensing::Module] License group:",
                "  Product: Unity Enterprise",
                "[Licensing::Client] Successfully updated license, isAsync: True, time: 0.00",
            ]
        )

        result = server_license.classify_license_log(text, exit_code=0)

        self.assertEqual("", result["batchmode_blocker_code"])

    def test_license_log_classification_ignores_recovered_ipc_startup_warning(self) -> None:
        text = "\n".join(
            [
                "[Licensing::IpcConnector] Channel LicenseClient-user doesn't exist",
                "[Licensing::Module] Successfully launched the LicensingClient (PId: 3769)",
                "[Licensing::Module] Successfully connected to LicensingClient on channel: \"LicenseClient-user\"",
                "Exiting batchmode successfully now!",
            ]
        )

        result = server_license.classify_license_log(text, exit_code=0)

        self.assertEqual("", result["batchmode_blocker_code"])

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

    def _manual_action_lane(self, project_root: Path, payload: dict):
        with (
            mock.patch.object(server, "process_visibility_summary", return_value={"process_visibility_available": True}),
            mock.patch.object(server, "list_live_project_editor_pids", return_value=[]),
            mock.patch.object(
                server,
                "build_license_capabilities",
                return_value={
                    "batchmode_supported": False,
                    "editor_ui_supported": None,
                    "batchmode_blocker_code": "licensing_client_ipc_failure",
                    "manual_user_action_required": True,
                    "licensing_handoff_classification": "manual_user_action_required",
                    "licensing_ipc_resolution": {"status": "no_hub_session"},
                    "recommended_execution_lane": "none",
                },
            ),
        ):
            return server.batch_lane_preflight_blocker(
                project_root=project_root,
                unity_app=Path("/Applications/FakeUnity.app"),
                batch_fallback_mode="auto",
                payload=payload,
                action_label="batch compile",
                timeout_ms=30000,
            )

    def test_batch_lane_preflight_still_refuses_manual_action_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            payload = {"action": "batch_compile_player_scripts"}
            with mock.patch.dict(os.environ, {server_license.GUI_ADMISSION_OVERRIDE_ENV: ""}, clear=False):
                with self.assertRaises(server_core.ToolInvocationError) as raised:
                    self._manual_action_lane(project_root, payload)

            self.assertEqual("manual_user_action_required", raised.exception.code)
            self.assertEqual(
                server_license.GUI_ADMISSION_OVERRIDE_ENV,
                raised.exception.details["gui_admission_override_env"],
            )
            self.assertIn("override", raised.exception.details["gui_admission_override_hint"])

    def test_batch_lane_preflight_admits_gui_under_a_recorded_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            payload = {"action": "batch_compile_player_scripts"}
            with mock.patch.dict(os.environ, {server_license.GUI_ADMISSION_OVERRIDE_ENV: "1"}, clear=False):
                lane, capabilities = self._manual_action_lane(project_root, payload)

            self.assertEqual("gui", lane)
            self.assertEqual("gui", payload["effective_execution_lane"])
            self.assertEqual("gui_admission_override", payload["lane_fallback_reason"])
            self.assertTrue(payload["gui_admission_override_active"])
            self.assertEqual(
                "licensing_client_ipc_failure",
                payload["gui_admission_override_waived_blocker"],
            )
            self.assertEqual(
                "manual_user_action_required",
                payload["gui_admission_override_waived_classification"],
            )
            self.assertFalse(capabilities["batchmode_supported"])

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

    def test_run_batch_operation_compact_dry_run_omits_command_vector(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            payload = {
                "action": "batch_compile_player_scripts",
                "project_root": str(project_root),
                "build_target": "Android",
                "result_file": str(project_root / "result.json"),
                "log_path": str(project_root / "batch.log"),
                "command": ["/Applications/Unity.app/Contents/MacOS/Unity", "-projectPath", str(project_root)],
                "dry_run": True,
            }
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                server.run_batch_operation(
                    project_root=project_root,
                    unity_app=Path("/Applications/FakeUnity.app"),
                    command=list(payload["command"]),
                    payload=payload,
                    log_path=project_root / "batch.log",
                    result_path=project_root / "result.json",
                    dry_run=True,
                    timeout_ms=30000,
                    progress_stdout=False,
                    batch_fallback_mode="auto",
                    output_mode="compact",
                )

            compact = json.loads(stdout.getvalue())
            self.assertEqual("compact_batch_cli", compact["payload_mode"])
            self.assertEqual("batch_compile_player_scripts", compact["action"])
            self.assertEqual("batch", compact["effective_execution_lane"])
            self.assertEqual("Android", compact["build_target"])
            self.assertTrue(compact["dry_run"])
            self.assertNotIn("command", compact)

    def test_compact_batch_cli_output_prefers_result_summary(self) -> None:
        payload = {
            "action": "batch_compile_matrix",
            "succeeded": True,
            "command": ["Unity", "-batchmode"],
            "summary_file": "/tmp/summary.json",
            "result_summary": {
                "action": "batch_compile_matrix",
                "transport_outcome": "batch_process_exited_cleanly",
                "unity_outcome": "passed",
                "succeeded": True,
                "batch_exit_code": 0,
                "matrix": {"status": "passed", "total": 2, "passed": 2, "failed": 0},
                "result_file": "/tmp/result.json",
                "raw_log_path": "/tmp/editor.log",
                "log_excerpt_hint": "warning line\n" * 100,
                "batchmode_probe_log_path": "/tmp/license-probe.log",
                "workspace_side_effects": {"paths": [f"/tmp/path-{index}" for index in range(100)]},
            },
        }

        compact = server_batch_reporting.batch_cli_output_payload(payload, "compact")

        self.assertEqual("compact_batch_cli", compact["payload_mode"])
        self.assertEqual("passed", compact["unity_outcome"])
        self.assertEqual({"status": "passed", "total": 2, "passed": 2, "failed": 0}, compact["matrix"])
        self.assertEqual("/tmp/summary.json", compact["summary_file"])
        self.assertNotIn("command", compact)
        self.assertNotIn("raw_log_path", compact)
        self.assertNotIn("log_excerpt_hint", compact)
        self.assertNotIn("batchmode_probe_log_path", compact)
        self.assertNotIn("workspace_side_effects", compact)
        encoded = json.dumps(compact, ensure_ascii=True, separators=(",", ":"))
        self.assertLessEqual(len(encoded.encode("utf-8")), 500)

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
                mock.patch.object(server_license, "live_editor_licensing_evidence", return_value={}),
            ):
                first = server_license.build_license_capabilities(project_root=project_root, refresh=True)
                second = server_license.build_license_capabilities(project_root=project_root, refresh=False)

            self.assertTrue(first["batchmode_supported"])
            self.assertEqual("batch", first["recommended_execution_lane"])
            self.assertTrue(second["from_cache"])
            self.assertEqual("2022.3.67f2", second["unity_version"])
            self.assertEqual(1, run_probe.call_count)

    ROUTINE_LICENSING_STARTUP_LOG = "\n".join(
        [
            "[Licensing::Module] Trying to connect to existing licensing client channel...",
            "[Licensing::IpcConnector] Channel LicenseClient-user doesn't exist",
            "Launching external process: /Applications/Unity/Unity.Licensing.Client",
            "[Licensing::Module] Successfully launched the LicensingClient (PId: 89259)",
            "[Package Manager] Connected to IPC stream \"Upm-89258\" after 0.3 seconds.",
            "[Licensing::Module] Licensing is not yet initialized.",
        ]
    )
    CONNECTION_LOST_LINE = (
        "[Licensing::Module] Error: The connection with the Unity Licensing Client has been lost. "
        "Attempting to reconnect."
    )

    @contextlib.contextmanager
    def _probe_environment(self, root: Path, live: dict | None = None):
        with contextlib.ExitStack() as stack:
            patches = {
                "detect_unity_app_path_for_project": root / "Unity.app",
                "resolve_unity_executable": root / "Unity",
                "resolve_unity_app_version": "6000.0.58f2",
                "live_editor_licensing_evidence": dict(live or {}),
                "resolve_hub_licensing_ipc": ({"status": "resolved"}, ""),
            }
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(server_license, name, return_value=value))
            yield

    def _write_verdict(
        self, path: Path, root: Path, *, supported, age_seconds: float, blocker: str = ""
    ) -> None:
        server_core.write_json(path, {
            "schema_version": server_license.LICENSE_CAPABILITIES_CACHE_SCHEMA,
            "cache_key": {"unity_executable_path": str(root / "Unity"), "unity_version": "6000.0.58f2"},
            "project_root": "/elsewhere/Other",
            "batchmode_supported": supported,
            "batchmode_blocker_code": blocker,
            "probe_completed_at": time.time() - age_seconds,
        })

    def _host_cache_path(self, root: Path) -> Path:
        key = {"unity_executable_path": str(root / "Unity"), "unity_version": "6000.0.58f2"}
        return server_license.licensing_host_state_dir() / (
            hashlib.sha256(json.dumps(key, sort_keys=True).encode("utf-8")).hexdigest() + ".json"
        )

    def test_routine_ipc_connector_lines_are_not_failure_evidence(self) -> None:
        for exit_code, timed_out in ((124, True), (1, False)):
            with self.subTest(exit_code=exit_code):
                result = server_license.classify_license_log(
                    self.ROUTINE_LICENSING_STARTUP_LOG, exit_code=exit_code, timed_out=timed_out
                )
                self.assertEqual("unknown_batch_failure", result["batchmode_blocker_code"])
        lost = server_license.classify_license_log(
            self.ROUTINE_LICENSING_STARTUP_LOG + "\n" + self.CONNECTION_LOST_LINE, exit_code=124, timed_out=True
        )
        self.assertEqual("licensing_client_ipc_failure", lost["batchmode_blocker_code"])
        connector_failure = server_license.classify_license_log(
            self.ROUTINE_LICENSING_STARTUP_LOG + "\n[Licensing::IpcConnector] Failed to connect to: LicenseClient-user",
            exit_code=1,
        )
        self.assertEqual("licensing_client_ipc_failure", connector_failure["batchmode_blocker_code"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def probe(command, **kwargs):
                log_path = Path(command[command.index("-logFile") + 1])
                log_path.write_text(self.ROUTINE_LICENSING_STARTUP_LOG, encoding="utf-8")
                raise server_license.subprocess.TimeoutExpired(command, kwargs.get("timeout"))

            with (
                self._probe_environment(root),
                mock.patch.object(server_license.subprocess, "run", side_effect=probe),
            ):
                result = server_license.build_license_capabilities(project_root=root, refresh=True, timeout_ms=1000)

        self.assertIsNone(result["batchmode_supported"])
        self.assertEqual("unknown_batch_failure", result["batchmode_blocker_code"])
        self.assertTrue(result["batchmode_probe_timed_out"])
        self.assertEqual("batch_diagnostic_required", result["recommended_execution_lane"])

    def test_only_a_negative_verdict_expires_and_only_into_a_quiet_host_reprobe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = server_license.license_capabilities_cache_path(root)
            completed = mock.Mock(returncode=0, stdout="", stderr="")
            with (
                self._probe_environment(root),
                mock.patch.object(server_license.subprocess, "run", return_value=completed) as run,
            ):
                for supported, age in ((False, 3600), (True, 30 * 24 * 3600), (None, 30 * 24 * 3600)):
                    with self.subTest(supported=supported, age=age):
                        self._write_verdict(cache, root, supported=supported, age_seconds=age)
                        kept = server_license.build_license_capabilities(project_root=root)
                        self.assertTrue(kept["from_cache"])
                        self.assertIs(kept["batchmode_supported"], supported)
                        run.assert_not_called()

                self._write_verdict(
                    cache, root, supported=False, age_seconds=2 * 24 * 3600, blocker="licensing_client_ipc_failure"
                )
                reprobed = server_license.build_license_capabilities(project_root=root)

            self.assertFalse(reprobed["from_cache"])
            self.assertTrue(reprobed["batchmode_supported"])
            self.assertEqual(1, run.call_count)

    def test_a_stale_negative_verdict_is_reused_while_an_editor_is_live(self) -> None:
        live_states = (
            {"editor_live": True},
            {"editor_live": True, "licensed_editor_live": True},
            {"visibility_unknown": True},
        )
        for live in live_states:
            with tempfile.TemporaryDirectory() as tmp, self.subTest(live=live):
                root = Path(tmp)
                cache = server_license.license_capabilities_cache_path(root)
                self._write_verdict(
                    cache, root, supported=False, age_seconds=20 * 24 * 3600, blocker="licensing_client_ipc_failure"
                )
                with (
                    self._probe_environment(root, live=live),
                    mock.patch.object(server_license.subprocess, "run") as run,
                ):
                    result = server_license.build_license_capabilities(project_root=root)
                run.assert_not_called()
                self.assertTrue(result["from_cache"])
                self.assertTrue(result["cache_verdict_stale"])
                self.assertEqual("stale_cache_editor_live", result["probe_skipped_reason"])
                self.assertFalse(result["batchmode_supported"])
                self.assertEqual("gui", result["recommended_execution_lane"])

    def test_a_proven_host_verdict_is_shared_but_a_negative_one_stays_project_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = server_license.license_capabilities_cache_path(root)
            host_cache = self._host_cache_path(root)
            with (
                self._probe_environment(root, live={"editor_live": True, "licensed_editor_live": True}),
                mock.patch.object(server_license.subprocess, "run") as run,
            ):
                self._write_verdict(
                    cache, root, supported=False, age_seconds=20 * 24 * 3600, blocker="licensing_client_ipc_failure"
                )
                self._write_verdict(host_cache, root, supported=True, age_seconds=24 * 3600)
                adopted = server_license.build_license_capabilities(project_root=root)
                self.assertTrue(adopted["batchmode_supported"])
                self.assertEqual("host_probe_cache", adopted["probe_skipped_reason"])
                self.assertEqual(str(root), adopted["project_root"])
                self.assertTrue(json.loads(cache.read_text(encoding="utf-8"))["batchmode_supported"])

                self._write_verdict(cache, root, supported=True, age_seconds=10 * 24 * 3600)
                self._write_verdict(
                    host_cache, root, supported=False, age_seconds=3600, blocker="no_valid_editor_license"
                )
                kept = server_license.build_license_capabilities(project_root=root)
                self.assertTrue(kept["batchmode_supported"])
                self.assertNotEqual("host_probe_cache", kept.get("probe_skipped_reason"))

                self._write_verdict(cache, root, supported=None, age_seconds=10 * 24 * 3600)
                inconclusive = server_license.build_license_capabilities(project_root=root)
                self.assertIsNone(inconclusive["batchmode_supported"])
                self.assertTrue(inconclusive["from_cache"])
            run.assert_not_called()

    def test_gui_fallback_failure_summary_carries_the_bridge_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {
                "action": "batch_compile_player_scripts",
                "start_editor_state": {"process_visibility_available": True, "live_project_editor_pids": []},
            }
            response = {
                "status": "error",
                "payload_json": "",
                "error": {
                    "code": "compile_errors_present",
                    "message": "Unity has compilation errors. Resolve them before running compile validation.",
                },
            }
            with (
                mock.patch.object(server, "open_unity_editor", return_value={"editor_pid": 42}),
                mock.patch.object(server, "wait_for_ready", return_value={"editor_pid": 42}),
                mock.patch.object(server, "update_host_editor_session_pid"),
                mock.patch.object(server, "refresh_project_context"),
                mock.patch.object(server, "invoke_bridge", return_value=response),
                mock.patch.object(
                    server,
                    "restore_host_opened_editor_state",
                    return_value={"same_project_editor_closed": True, "process_exit_verified": True},
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                with self.assertRaises(SystemExit):
                    server.run_gui_fallback_operation(
                        project_root=root,
                        unity_app=root / "Unity.app",
                        payload=payload,
                        action_label="batch compile",
                        operation="unity.compile.player_scripts",
                        operation_args={"target": "Android"},
                        timeout_ms=1000,
                        log_path=root / "gui.log",
                        result_path=root / "result.json",
                        summary_path=root / "result_summary.json",
                        side_effect_mode="off",
                    )

            summary = json.loads((root / "result_summary.json").read_text(encoding="utf-8"))
            self.assertEqual("gui_operation_failed", summary["transport_outcome"])
            self.assertEqual("compile_errors_present", summary["gui_operation_error_code"])
            self.assertIn("Unity has compilation errors", summary["top_actionable_error"])
            self.assertIn("Unity has compilation errors", summary["terminal_record"]["top_actionable_error"])
            compact = server_batch_reporting.batch_cli_output_payload(payload, "compact")
            self.assertEqual("compile_errors_present", compact["gui_operation_error_code"])
            self.assertIn("Unity has compilation errors", compact["top_actionable_error"])

    def test_mcp_license_capabilities_tool_returns_structured_content(self) -> None:
        payload = {"action": "license_capabilities", "batchmode_supported": True}
        with (
            mock.patch.object(server, "ensure_project_root", return_value=Path("/tmp/FakeProject")),
            mock.patch.object(server, "detect_unity_app_path_for_project", return_value=Path("/tmp/Unity.app")),
            mock.patch.object(server, "build_license_capabilities", return_value=payload),
        ):
            result = server.call_unity_license_capabilities_tool(
                {"projectRoot": "/tmp/FakeProject", "timeoutMs": 1000}
            )

        self.assertFalse(result["isError"])
        self.assertEqual(payload, result["structuredContent"])
        self.assertEqual(payload, json.loads(result["content"][0]["text"]))


if __name__ == "__main__":
    unittest.main()
