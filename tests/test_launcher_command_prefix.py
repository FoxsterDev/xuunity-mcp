import ast
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path, PureWindowsPath
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
for entry in (TESTS_DIR, TEMPLATES_DIR):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from bash_support import resolve_bash_executable, run_with_timeout, skip_if_prior_subprocess_timeout

import server
import server_batch_recovery
import server_bridge_request_artifacts
import server_bridge_transport
import server_cli_bridge_commands
import server_core
import server_editor_host
import server_launcher
from server_core import ToolInvocationError
from server_recovery_commands import recommended_recovery_command_for_project

NAME_ENV = "XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME"
PATH_ENV = "XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_PATH"


def launcher_env(name: str = "", path: str = "") -> dict:
    return {NAME_ENV: name, PATH_ENV: path}


def make_launcher(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    launcher = directory / name
    launcher.write_text("#!/usr/bin/env bash\nfor arg in \"$@\"; do printf '%s\\n' \"$arg\"; done\n", encoding="utf-8")
    launcher.chmod(0o755)
    return launcher


class LauncherCommandPrefixTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.launcher_dir = Path(self._tmp.name) / "Application Support" / "xuunity-mcp"

    def test_unset_path_falls_back_to_bare_name(self) -> None:
        with mock.patch.dict(os.environ, launcher_env("xuunity_light_unity_mcp.sh")):
            self.assertEqual("xuunity_light_unity_mcp.sh", server_core.launcher_command_prefix())

    def test_existing_launcher_renders_quoted_absolute_posix_path(self) -> None:
        launcher = make_launcher(self.launcher_dir, "run_installed_or_refresh_xuunity_mcp.sh")
        with mock.patch.dict(os.environ, launcher_env(launcher.name, str(launcher))):
            prefix = server_core.launcher_command_prefix()
        self.assertEqual(f'"{launcher.as_posix()}"', prefix)
        self.assertIn("Application Support", prefix)

    def test_missing_mismatched_relative_or_quoted_path_falls_back(self) -> None:
        launcher = make_launcher(self.launcher_dir, "run_installed_or_refresh_xuunity_mcp.sh")
        cases = {
            "missing": launcher_env(launcher.name, str(self.launcher_dir / "gone" / launcher.name)),
            "mismatch": launcher_env("xuunity_light_unity_mcp.sh", str(launcher)),
            "relative": launcher_env(launcher.name, launcher.name),
            "quoted": launcher_env(launcher.name, f'"{launcher}"'),
        }
        for label, env in cases.items():
            with self.subTest(label), mock.patch.dict(os.environ, env):
                self.assertEqual(env[NAME_ENV], server_core.launcher_command_prefix())

    def test_ps1_launcher_gets_call_operator(self) -> None:
        launcher = make_launcher(self.launcher_dir, "xuunity_light_unity_mcp.ps1")
        with mock.patch.dict(os.environ, launcher_env(launcher.name, str(launcher))):
            prefix = server_core.launcher_command_prefix()
        self.assertEqual(f'& "{launcher.as_posix()}"', prefix)

    def test_windows_like_host_keeps_forward_slash_token_and_native_project_root(self) -> None:
        launcher = make_launcher(self.launcher_dir, "xuunity_light_unity_mcp.cmd")
        with (
            mock.patch.dict(os.environ, launcher_env(launcher.name, str(launcher))),
            mock.patch.object(server_core, "is_windows_like_host", return_value=True),
        ):
            command = server_core.render_launcher_cli("ensure-ready", PureWindowsPath("C:/tmp/Fake Project"), "--open-editor")
        token = f'"{launcher.as_posix()}"'
        self.assertTrue(command.startswith(token + " ensure-ready "), command)
        self.assertNotIn("\\", token)
        self.assertIn('--project-root "C:\\tmp\\Fake Project" --open-editor', command)


class RenderedRecoveryCommandsUseLauncherPrefixTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.temp_root = Path(self._tmp.name)
        self.launcher = make_launcher(self.temp_root / "Application Support" / "xuunity-mcp", "xuunity_light_unity_mcp.sh")
        self.token = f'"{self.launcher.as_posix()}"'
        patches = [
            mock.patch.dict(os.environ, launcher_env(self.launcher.name, str(self.launcher))),
            mock.patch.object(server_core, "is_windows_like_host", return_value=False),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.project_root = self.temp_root / "Unity Projects" / "Fake Project"
        (self.project_root / "Assets").mkdir(parents=True)
        (self.project_root / "ProjectSettings").mkdir(parents=True)
        (self.project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: 2021.3.58f1\n", encoding="utf-8"
        )

    def assert_bridge_enable_message(self, message: str) -> None:
        self.assertIn(f"{self.token} setup-plan --project-root <path>", message)
        self.assertIn(f"then {self.token} setup-apply --plan-file <plan>", message)

    def test_render_launcher_cli_and_recovery_map_start_with_quoted_launcher(self) -> None:
        self.assertTrue(server_core.render_launcher_cli("ensure-ready", self.project_root).startswith(self.token + " "))
        for action in ("ensure_ready_or_recover_bridge", "scaffold_project_hook", "recover_editor_session"):
            with self.subTest(action):
                self.assertTrue(recommended_recovery_command_for_project(self.project_root, action).startswith(self.token + " "))
                self.assertTrue(server.recommended_recovery_command_for_project(self.project_root, action).startswith(self.token + " "))
        enable = server.recommended_recovery_command_for_project(self.project_root, "enable_bridge_and_retry")
        self.assertTrue(enable.startswith(f'{self.token} setup-plan --project-root "{self.project_root.as_posix()}"'), enable)

    def test_bridge_enable_helper_fills_launcher(self) -> None:
        self.assert_bridge_enable_message(server_core.bridge_enable_recovery_command())

    def test_no_template_formats_bridge_enable_recipe_directly(self) -> None:
        for path in TEMPLATES_DIR.glob("server*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Attribute)
                    and node.attr == "format"
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "BRIDGE_ENABLE_RECOVERY_COMMAND"
                    and path.name != "server_core.py"
                ):
                    self.fail(f"{path.name}:{node.lineno} formats BRIDGE_ENABLE_RECOVERY_COMMAND without the helper")

    def test_wait_for_ready_bridge_disabled_message(self) -> None:
        with self.assertRaises(ToolInvocationError) as raised:
            server_editor_host.wait_for_ready(
                self.project_root, 1000, 5, "fail_fast_on_interactive_compile_block", self.project_root / "Editor.log"
            )
        self.assertEqual("bridge_disabled", raised.exception.code)
        self.assert_bridge_enable_message(raised.exception.message)

    def test_invoke_bridge_transport_bridge_disabled_message(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(ToolInvocationError) as raised:
            server_bridge_transport.invoke_bridge_transport(self.project_root, "unity.status", {}, 1000)
        self.assertEqual("bridge_disabled", raised.exception.code)
        self.assert_bridge_enable_message(raised.exception.message)

    def test_cli_bridge_state_bridge_disabled_message(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            server_cli_bridge_commands.cmd_bridge_state(types.SimpleNamespace(project_root=str(self.project_root)))
        self.assert_bridge_enable_message(str(raised.exception.code))

    def reconciliation_context(self):
        return types.SimpleNamespace(
            discovery_details={
                "reconciliation_case": "bridge_disabled",
                "reconciliation_status": "offline",
                "reconciliation_recommended_next_action": "enable_bridge_and_retry",
                "detected_editor_count": 0,
                "detected_editor_pids": [],
            },
            last_bridge_state={},
        )

    def test_orchestrator_reconciliation_bridge_disabled_message(self) -> None:
        context = self.reconciliation_context()
        registry = types.SimpleNamespace(refresh_context=lambda _: context)
        with (
            mock.patch.object(server, "_BRIDGE_REGISTRY", registry),
            mock.patch.object(server, "read_best_effort_bridge_state", return_value=None),
            self.assertRaises(ToolInvocationError) as raised,
        ):
            server.recover_project_bridge_for_reconciliation(
                self.project_root,
                timeout_ms=1000,
                heartbeat_max_age_seconds=5,
                startup_policy="fail_fast_on_interactive_compile_block",
                allow_open_editor=False,
            )
        self.assertEqual("bridge_disabled", raised.exception.code)
        self.assert_bridge_enable_message(raised.exception.message)

    def test_batch_recovery_reconciliation_bridge_disabled_message(self) -> None:
        context = self.reconciliation_context()
        with (
            mock.patch.object(server_batch_recovery, "current_project_context_bridge_state", return_value={}),
            mock.patch.object(
                server_batch_recovery, "current_project_context_discovery_details", return_value=context.discovery_details
            ),
            mock.patch.object(server_batch_recovery, "bridge_state_is_ready", return_value=False),
            mock.patch.object(server_batch_recovery, "execute_host_health_recovery_policy", return_value={"action": "none"}),
            mock.patch.object(server_batch_recovery, "enrich_tool_invocation_error_with_discovery", side_effect=lambda _root, exc: exc),
            self.assertRaises(ToolInvocationError) as raised,
        ):
            server_batch_recovery.recover_project_bridge_for_reconciliation(
                self.project_root,
                timeout_ms=1000,
                heartbeat_max_age_seconds=5,
                startup_policy="fail_fast_on_interactive_compile_block",
                allow_open_editor=False,
            )
        self.assertEqual("bridge_disabled", raised.exception.code)
        self.assert_bridge_enable_message(raised.exception.message)

    def test_cancel_request_recovery_command_quotes_launcher_and_root(self) -> None:
        with (
            mock.patch.object(server_bridge_request_artifacts, "read_best_effort_bridge_state", return_value={}),
            mock.patch.object(
                server_bridge_request_artifacts,
                "read_request_journal_events",
                return_value=[{"event_type": "request_completed", "operation": "unity.status"}],
            ),
        ):
            result = server_bridge_request_artifacts.cancel_request_best_effort(self.project_root, "req-1")
        expected = f'{self.token} request-final-status --project-root "{self.project_root.as_posix()}" --request-id req-1'
        self.assertEqual(expected, result.get("recommended_recovery_command"))

    def test_restore_host_opened_editor_quit_recovery_command_quotes_launcher_and_root(self) -> None:
        session = {"opened_by_host": True, "editor_pid": 4242}
        with (
            mock.patch.object(server_editor_host, "try_read_host_editor_session_state", return_value=session),
            mock.patch.object(server_editor_host, "try_read_live_editor_state", return_value={"editor_pid": 4242}),
            mock.patch.object(server_editor_host, "verify_project_editor_closed", return_value={"process_visibility_available": False}),
            mock.patch.object(server_editor_host, "wait_for_project_editor_exit", return_value=(True, [])),
        ):
            restoration = server_editor_host.restore_host_opened_editor_state(
                self.project_root,
                1000,
                lambda _root, _timeout: {"status": "ok", "request_id": "quit-1"},
            )
        expected = f'{self.token} request-final-status --project-root "{self.project_root.as_posix()}" --request-id quit-1'
        self.assertEqual(expected, restoration.get("recommended_recovery_command"), restoration)

class LauncherPathPublishingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.script_dir = Path(self._tmp.name) / "Application Support" / "xuunity-mcp"
        self.script_dir.mkdir(parents=True)

    def load_refresh_launcher_module(self):
        spec = importlib.util.spec_from_file_location(
            "run_installed_or_refresh_xuunity_mcp_prefix_test",
            REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.py",
        )
        module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)
        return module

    def test_refresh_launcher_publishes_its_own_path(self) -> None:
        module = self.load_refresh_launcher_module()
        sh = make_launcher(self.script_dir, "run_installed_or_refresh_xuunity_mcp.sh")
        cmd = make_launcher(self.script_dir, "run_installed_or_refresh_xuunity_mcp.cmd")
        cases = [
            ("posix", sh.name, sh),
            ("nt", "", cmd),
            ("posix", "xuunity_light_unity_mcp.sh", sh),
        ]
        for os_name, inherited_name, expected in cases:
            with self.subTest(os_name=os_name, inherited_name=inherited_name):
                with (
                    mock.patch.dict(os.environ, launcher_env(inherited_name, "/stale/launcher")),
                    mock.patch.object(module.os, "name", os_name),
                ):
                    module.publish_launcher_env(self.script_dir)
                    self.assertEqual(expected.name, os.environ[NAME_ENV])
                    self.assertEqual(str(expected), os.environ[PATH_ENV])

    def test_refresh_launcher_without_launcher_file_drops_stale_path(self) -> None:
        module = self.load_refresh_launcher_module()
        with mock.patch.dict(os.environ, launcher_env("run_installed_or_refresh_xuunity_mcp.sh", "/stale/launcher")):
            module.publish_launcher_env(self.script_dir)
            self.assertNotIn(PATH_ENV, os.environ)

    def test_source_launcher_publishes_repo_wrapper_path(self) -> None:
        root = Path(self._tmp.name) / "source checkout"
        make_launcher(root, "xuunity_light_unity_mcp.sh")
        make_launcher(root, "xuunity_light_unity_mcp.cmd")
        cases = [
            ("xuunity_light_unity_mcp.sh", "posix", "xuunity_light_unity_mcp.sh"),
            ("run_installed_or_refresh_xuunity_mcp.cmd", "nt", "xuunity_light_unity_mcp.cmd"),
        ]
        with mock.patch.object(server_launcher, "_LAUNCHER_DIR", root / "templates"):
            for inherited_name, os_name, expected in cases:
                with self.subTest(inherited_name=inherited_name):
                    with (
                        mock.patch.dict(os.environ, launcher_env(inherited_name, "/stale/launcher")),
                        mock.patch.object(server_launcher.os, "name", os_name),
                    ):
                        server_launcher.publish_launcher_path_env()
                        self.assertEqual(expected, os.environ[NAME_ENV])
                        self.assertEqual(str(root / expected), os.environ[PATH_ENV])
            for inherited_name in ("xuunity_light_unity_mcp.ps1", "custom-launcher"):
                with self.subTest(inherited_name=inherited_name):
                    with mock.patch.dict(os.environ, launcher_env(inherited_name, "/stale/launcher")):
                        server_launcher.publish_launcher_path_env()
                        self.assertNotIn(PATH_ENV, os.environ)


class RenderedCommandRunsVerbatimTests(unittest.TestCase):
    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)

    def test_rendered_command_runs_from_any_cwd_in_bash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            launcher = make_launcher(temp_root / "Application Support \u0416", "xuunity_light_unity_mcp.sh")
            project_root = temp_root / "Fake Project"
            elsewhere = temp_root / "elsewhere"
            elsewhere.mkdir()
            with mock.patch.dict(os.environ, launcher_env(launcher.name, str(launcher))):
                rendered = server_core.render_launcher_cli("ensure-ready", project_root, "--open-editor")
            completed = run_with_timeout(
                [resolve_bash_executable(), "-c", rendered], cwd=str(elsewhere), timeout_seconds=60
            )
        self.assertEqual(0, completed.returncode, completed.stderr)
        argv = completed.stdout.splitlines()
        self.assertEqual(["ensure-ready", "--project-root"], argv[:2])
        self.assertEqual(project_root, Path(argv[2]))
        self.assertEqual(["--open-editor"], argv[3:])


if __name__ == "__main__":
    unittest.main()
