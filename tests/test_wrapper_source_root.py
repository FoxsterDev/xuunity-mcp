import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from bash_support import resolve_bash_executable, run_with_timeout, skip_if_prior_subprocess_timeout

REPO_ROOT = Path(__file__).resolve().parents[1]


class WrapperSourceRootTests(unittest.TestCase):
    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)

    def make_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["PYTHON"] = sys.executable
        # Isolate neutral install dir from host environment
        env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = "/tmp/nonexistent-xuunity-neutral-dir"
        return env

    def create_fake_project(self, root: Path, unity_version: str = "2021.3.58f1") -> Path:
        (root / "Assets").mkdir(parents=True)
        (root / "Packages").mkdir(parents=True)
        (root / "ProjectSettings").mkdir(parents=True)
        (root / "Packages" / "manifest.json").write_text(
            json.dumps({"dependencies": {}}, indent=2) + "\n",
            encoding="utf-8",
        )
        (root / "ProjectSettings" / "ProjectVersion.txt").write_text(
            f"m_EditorVersion: {unity_version}\n",
            encoding="utf-8",
        )
        return root

    def run_git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )

    def get_wrapper_cmd(self, wrapper_path: Path) -> list[str]:
        if os.name == "nt" or sys.platform == "win32":
            return [resolve_bash_executable(), wrapper_path.as_posix()]
        return [str(wrapper_path)]

    def load_refresh_launcher_module(self):
        spec = importlib.util.spec_from_file_location(
            "run_installed_or_refresh_xuunity_mcp",
            REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.py",
        )
        module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)
        return module

    def test_refresh_python_prefers_git_bash_over_system32_bash_on_windows(self) -> None:
        module = self.load_refresh_launcher_module()

        class HostPath:
            def __init__(self, *parts: str) -> None:
                self.value = os.path.join(*(str(part) for part in parts))

            def joinpath(self, *parts: str):
                return HostPath(self.value, *parts)

            def is_file(self) -> bool:
                return os.path.isfile(self.value)

            def __str__(self) -> str:
                return self.value

        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_program_files = Path(tmp_dir) / "Program Files"
            git_bash = fake_program_files / "Git" / "usr" / "bin" / "bash.exe"
            git_bash.parent.mkdir(parents=True)
            git_bash.write_text("", encoding="utf-8")

            with (
                mock.patch.object(module.os, "name", "nt"),
                mock.patch.dict(
                    module.os.environ,
                    {
                        "PROGRAMFILES": str(fake_program_files),
                        "ProgramW6432": "",
                        "PROGRAMFILES(X86)": "",
                    },
                    clear=False,
                ),
                mock.patch.object(module, "Path", HostPath),
                mock.patch.object(module.shutil, "which", return_value=r"C:\Windows\System32\bash.exe"),
            ):
                self.assertEqual(str(git_bash), module.find_bash())

    def test_refresh_python_uses_run_cmd_for_windows_exec(self) -> None:
        module = self.load_refresh_launcher_module()

        with tempfile.TemporaryDirectory() as tmp_dir:
            run_cmd = Path(tmp_dir) / "run.cmd"
            run_cmd.write_text("@echo off\n", encoding="utf-8")

            with (
                mock.patch.object(module.os, "name", "nt"),
                mock.patch.object(module.subprocess, "run") as run_mock,
            ):
                run_mock.return_value = subprocess.CompletedProcess([str(run_cmd), "--help"], 7)
                with self.assertRaises(SystemExit) as raised:
                    module.exec_run(run_cmd, ["--help"])

        self.assertEqual(7, raised.exception.code)
        run_mock.assert_called_once_with([str(run_cmd), "--help"], check=False)

    @unittest.skipUnless(os.name == "nt", "native Windows .cmd smoke")
    def test_refresh_cmd_print_run_uses_windows_low_level_launcher(self) -> None:
        refresh_cmd = REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.cmd"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            env = self.make_env()
            env["CODEX_HOME"] = str(temp_root / "codex-home")
            env["CODEX_TOOLS_HOME"] = str(temp_root / "codex-tools")
            env["CLAUDE_TOOLS_HOME"] = str(temp_root / "claude-tools")
            env["CLAUDE_CONFIG_PATH"] = str(temp_root / "claude.json")
            env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(temp_root / "neutral")

            completed = run_with_timeout(
                ["cmd.exe", "/c", str(refresh_cmd), "--print-run"],
                env=env,
                timeout_seconds=120,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(completed.stdout.strip().endswith("run.cmd"), completed.stdout)

    def test_wrapper_honors_python_command_name_without_recursive_function_crash(self) -> None:
        wrapper = REPO_ROOT / "xuunity_light_unity_mcp.sh"
        env = self.make_env()
        env["PYTHON"] = "python3"

        completed = run_with_timeout(
            self.get_wrapper_cmd(wrapper) + ["--help"],
            env=env,
            timeout_seconds=120,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("Usage:", completed.stdout)

    def test_wrapper_supports_windows_py_launcher_style_python_env(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_py = Path(tmp_dir) / "py"
            fake_py.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"${1:-}\" == \"-3\" ]]; then shift; fi\n"
                f"exec {sys.executable!r} \"$@\"\n",
                encoding="utf-8",
            )
            fake_py.chmod(0o755)

            env = self.make_env()
            env["PYTHON"] = "py -3"
            env["PATH"] = f"{tmp_dir}{os.pathsep}{env.get('PATH', '')}"

            completed = run_with_timeout(
                self.get_wrapper_cmd(wrapper) + ["--help"],
                env=env,
                timeout_seconds=120,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("Usage:", completed.stdout)

    def test_run_sh_template_supports_windows_py_launcher_style_python_env(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        run_sh = repo_root / "templates" / "run.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_py = Path(tmp_dir) / "py"
            fake_py.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"${1:-}\" == \"-3\" ]]; then shift; fi\n"
                f"exec {sys.executable!r} \"$@\"\n",
                encoding="utf-8",
            )
            fake_py.chmod(0o755)

            env = self.make_env()
            env["PYTHON"] = "py -3"
            env["PATH"] = f"{tmp_dir}{os.pathsep}{env.get('PATH', '')}"

            completed = run_with_timeout(
                [resolve_bash_executable(), run_sh.as_posix(), "--help"],
                env=env,
                timeout_seconds=120,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("usage:", completed.stdout.lower())

    def test_devmode_prefers_operations_package_source_under_airroot(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            airroot = temp_root / "AIRoot"
            root_package = airroot / "packages" / "com.xuunity.light-mcp"
            operation_root = airroot / "Operations" / "XUUnityLightUnityMcp"
            operation_package = operation_root / "packages" / "com.xuunity.light-mcp"

            for root in (airroot, operation_root):
                (root / "templates").mkdir(parents=True, exist_ok=True)
                (root / "templates" / "server.py").write_text("# fake server\n", encoding="utf-8")
            for package in (root_package, operation_package):
                package.mkdir(parents=True, exist_ok=True)
                (package / "package.json").write_text('{"name":"com.xuunity.light-mcp"}\n', encoding="utf-8")

            project_root = temp_root / "FakeProject"
            (project_root / "Packages").mkdir(parents=True)
            (project_root / "ProjectSettings").mkdir(parents=True)
            (project_root / "Packages" / "manifest.json").write_text(
                json.dumps({"dependencies": {}}, indent=2) + "\n",
                encoding="utf-8",
            )
            (project_root / "Packages" / "packages-lock.json").write_text(
                json.dumps({"dependencies": {"com.xuunity.light-mcp": {"version": "old"}}}, indent=2) + "\n",
                encoding="utf-8",
            )
            (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 6000.0.58f2\n",
                encoding="utf-8",
            )

            env = self.make_env()
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT", None)
            env["XUUNITY_LIGHT_UNITY_MCP_AIRROOT"] = str(airroot)

            completed = run_with_timeout(
                self.get_wrapper_cmd(wrapper) + ["devmode", "--project-root", str(project_root)],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            manifest = json.loads((project_root / "Packages" / "manifest.json").read_text(encoding="utf-8"))
            dependency = manifest["dependencies"]["com.xuunity.light-mcp"]
            resolved_dependency = (project_root / "Packages" / dependency.removeprefix("file:")).resolve()
            self.assertEqual(operation_package.resolve(), resolved_dependency)
            package_source_lines = [
                line for line in completed.stdout.splitlines() if line.startswith("package_source=")
            ]
            self.assertEqual(1, len(package_source_lines), completed.stdout)
            package_source_value = package_source_lines[0].removeprefix("package_source=").replace("\\", "/")
            self.assertTrue(
                package_source_value.endswith(
                    "AIRoot/Operations/XUUnityLightUnityMcp/packages/com.xuunity.light-mcp"
                ),
                completed.stdout,
            )

    def test_setup_plan_default_version_uses_source_without_installed_helper_sync(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"
        package_json = repo_root / "packages" / "com.xuunity.light-mcp" / "package.json"
        package_version = json.loads(package_json.read_text(encoding="utf-8"))["version"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = self.create_fake_project(temp_root / "FakeProject")
            codex_tools = temp_root / "codex-tools"
            claude_tools = temp_root / "claude-tools"

            env = self.make_env()
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SERVER", None)
            env["CODEX_TOOLS_HOME"] = str(codex_tools)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)

            completed = run_with_timeout(
                self.get_wrapper_cmd(wrapper) + ["setup-plan", "--project-root", str(project_root)],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            plan = json.loads(completed.stdout)
            actions = plan["projects"][0]["planned_actions"]
            dependency_actions = [action for action in actions if action["kind"] == "set_manifest_dependency"]
            self.assertEqual(1, len(dependency_actions))
            self.assertTrue(dependency_actions[0]["value"].endswith(f"#v{package_version}"))

            installed_package_json = (
                codex_tools
                / "xuunity-mcp"
                / "packages"
                / "com.xuunity.light-mcp"
                / "package.json"
            )
            self.assertFalse(installed_package_json.exists())

    def test_uninstall_plan_uses_source_without_installed_helper_sync(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = self.create_fake_project(temp_root / "FakeProject")
            codex_tools = temp_root / "codex-tools"
            claude_tools = temp_root / "claude-tools"

            env = self.make_env()
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SERVER", None)
            env["CODEX_TOOLS_HOME"] = str(codex_tools)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)

            completed = run_with_timeout(
                self.get_wrapper_cmd(wrapper) + [
                    "uninstall-plan",
                    "--mode",
                    "project-only-cleanup",
                    "--project-root",
                    str(project_root),
                ],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            plan = json.loads(completed.stdout)
            self.assertEqual("uninstall_plan", plan["action"])
            self.assertEqual("project-only-cleanup", plan["mode"])
            self.assertFalse((codex_tools / "xuunity-mcp").exists())
            self.assertFalse((claude_tools / "xuunity-mcp").exists())

    def test_auto_install_target_prefers_codex_home_in_codex_context(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = self.create_fake_project(temp_root / "FakeProject")
            codex_tools = temp_root / "codex-tools"
            claude_tools = temp_root / "claude-tools"
            stale_claude_install = claude_tools / "xuunity-mcp"
            stale_claude_install.mkdir(parents=True)
            stale_server = stale_claude_install / "server.py"
            stale_server.write_text("# stale claude helper\n", encoding="utf-8")

            env = self.make_env()
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SERVER", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET", None)
            env["CODEX_TOOLS_HOME"] = str(codex_tools)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)
            env["CODEX_SHELL"] = "1"

            completed = run_with_timeout(
                self.get_wrapper_cmd(wrapper) + ["server-help"],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue((codex_tools / "xuunity-mcp" / "server.py").is_file())
            self.assertEqual("# stale claude helper\n", stale_server.read_text(encoding="utf-8"))

    def test_init_installs_refresh_launcher_and_registers_it_in_codex_config(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        init_script = repo_root / "init_xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            codex_home = temp_root / "codex-home"
            codex_tools = temp_root / "codex-tools"
            claude_tools = temp_root / "claude-tools"
            neutral_dir = temp_root / "neutral"

            env = self.make_env()
            env["CODEX_HOME"] = str(codex_home)
            env["CODEX_TOOLS_HOME"] = str(codex_tools)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)
            env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(neutral_dir)

            completed = run_with_timeout(
                [resolve_bash_executable(), init_script.as_posix(), "--target", "codex", "--install-codex-config"],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            codex_install = codex_tools / "xuunity-mcp"
            neutral_refresh = neutral_dir / "run_installed_or_refresh_xuunity_mcp.sh"
            neutral_refresh_py = neutral_dir / "run_installed_or_refresh_xuunity_mcp.py"
            neutral_refresh_cmd = neutral_dir / "run_installed_or_refresh_xuunity_mcp.cmd"
            codex_refresh = codex_install / "run_installed_or_refresh_xuunity_mcp.sh"
            codex_refresh_py = codex_install / "run_installed_or_refresh_xuunity_mcp.py"
            codex_refresh_cmd = codex_install / "run_installed_or_refresh_xuunity_mcp.cmd"
            self.assertTrue(neutral_refresh.is_file())
            self.assertTrue(os.access(neutral_refresh, os.X_OK))
            self.assertTrue(neutral_refresh_py.is_file())
            self.assertTrue(neutral_refresh_cmd.is_file())
            self.assertTrue(codex_refresh.is_file())
            self.assertTrue(os.access(codex_refresh, os.X_OK))
            self.assertTrue(codex_refresh_py.is_file())
            self.assertTrue(codex_refresh_cmd.is_file())
            self.assertEqual(repo_root.resolve(), Path((neutral_dir / ".source_root").read_text(encoding="utf-8").strip()).resolve())

            config_text = (codex_home / "config.toml").read_text(encoding="utf-8")
            if env.get("OS") == "Windows_NT" or env.get("APPDATA") or os.name == "nt":
                self.assertIn('command = "cmd.exe"', config_text)
                self.assertIn("run_installed_or_refresh_xuunity_mcp.cmd", config_text)
                self.assertNotIn("run_installed_or_refresh_xuunity_mcp.sh", config_text)
            else:
                self.assertIn("run_installed_or_refresh_xuunity_mcp.sh", config_text)
                self.assertNotIn('command = "cmd.exe"', config_text)
            self.assertNotIn("/xuunity-mcp/run.sh", config_text)

    def test_init_registers_native_windows_codex_config_on_windows_like_host(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        init_script = repo_root / "init_xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            codex_home = temp_root / "codex-home"
            codex_tools = temp_root / "codex-tools"
            claude_tools = temp_root / "claude-tools"
            neutral_dir = temp_root / "neutral"

            env = self.make_env()
            env["CODEX_HOME"] = str(codex_home)
            env["CODEX_TOOLS_HOME"] = str(codex_tools)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)
            env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(neutral_dir)
            env["OS"] = "Windows_NT"
            env["APPDATA"] = str(temp_root / "AppData" / "Roaming")
            env["USERPROFILE"] = str(temp_root)

            completed = run_with_timeout(
                [resolve_bash_executable(), init_script.as_posix(), "--target", "codex", "--install-codex-config"],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            config_text = (codex_home / "config.toml").read_text(encoding="utf-8")
            self.assertIn('command = "cmd.exe"', config_text)
            self.assertIn("run_installed_or_refresh_xuunity_mcp.cmd", config_text)
            self.assertNotIn('command = "bash"', config_text)
            self.assertNotIn("run_installed_or_refresh_xuunity_mcp.sh", config_text)

    def test_init_registers_native_windows_claude_config_on_windows_like_host(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        init_script = repo_root / "init_xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            claude_config = temp_root / "claude.json"
            claude_tools = temp_root / "claude-tools"
            neutral_dir = temp_root / "neutral"

            env = self.make_env()
            env["CLAUDE_CONFIG_PATH"] = str(claude_config)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)
            env["CODEX_TOOLS_HOME"] = str(temp_root / "codex-tools")
            env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(neutral_dir)
            env["OS"] = "Windows_NT"
            env["APPDATA"] = str(temp_root / "AppData" / "Roaming")
            env["USERPROFILE"] = str(temp_root)

            completed = run_with_timeout(
                [resolve_bash_executable(), init_script.as_posix(), "--target", "claude", "--install-claude-config"],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            config = json.loads(claude_config.read_text(encoding="utf-8"))
            server_entry = config["mcpServers"]["xuunity_light_unity"]
            self.assertEqual("cmd.exe", server_entry["command"])
            self.assertEqual(["/d", "/c", "call"], server_entry["args"][:3])
            launcher_arg = server_entry["args"][3]
            self.assertTrue(
                launcher_arg.endswith("run_installed_or_refresh_xuunity_mcp.cmd"), launcher_arg
            )
            self.assertIn(
                "claude-tools",
                launcher_arg,
                "claude target must resolve the CLAUDE_TOOLS_HOME install dir at write time",
            )
            for arg in server_entry["args"]:
                self.assertNotRegex(
                    arg,
                    r'["()]',
                    "client argv quoting escapes embedded quotes as \\\" — "
                    f"config args must stay quote-free: {arg!r}",
                )

    def test_init_replaces_windows_bash_claude_config_with_cmd_launcher(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        init_script = repo_root / "init_xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            claude_config = temp_root / "claude.json"
            claude_config.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "xuunity_light_unity": {
                                "type": "stdio",
                                "command": "bash",
                                "args": ["-lc", 'exec "/home/user/.claude-tools/xuunity-mcp/run.sh"'],
                            },
                            "other_server": {"type": "stdio", "command": "other"},
                        }
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            neutral_dir = temp_root / "neutral"

            env = self.make_env()
            env["CLAUDE_CONFIG_PATH"] = str(claude_config)
            env["CLAUDE_TOOLS_HOME"] = str(temp_root / "claude-tools")
            env["CODEX_TOOLS_HOME"] = str(temp_root / "codex-tools")
            env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(neutral_dir)
            env["OS"] = "Windows_NT"
            env["APPDATA"] = str(temp_root / "AppData" / "Roaming")
            env["USERPROFILE"] = str(temp_root)

            completed = run_with_timeout(
                [resolve_bash_executable(), init_script.as_posix(), "--target", "claude", "--install-claude-config"],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("windows_claude_launcher_mismatch", completed.stderr)
            config = json.loads(claude_config.read_text(encoding="utf-8"))
            server_entry = config["mcpServers"]["xuunity_light_unity"]
            self.assertEqual("cmd.exe", server_entry["command"])
            self.assertIn("other_server", config["mcpServers"])

    def test_init_delegate_cmd_files_are_crlf_and_delegate_py_avoids_execv_on_windows(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        init_script = repo_root / "init_xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            claude_tools = temp_root / "claude-tools"
            neutral_dir = temp_root / "neutral"

            env = self.make_env()
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)
            env["CODEX_TOOLS_HOME"] = str(temp_root / "codex-tools")
            env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(neutral_dir)

            completed = run_with_timeout(
                [resolve_bash_executable(), init_script.as_posix(), "--target", "claude"],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            claude_install = claude_tools / "xuunity-mcp"
            for name in ("run.cmd", "run_installed_or_refresh_xuunity_mcp.cmd"):
                data = (claude_install / name).read_bytes()
                self.assertIn(b"\r\n", data, name)
                self.assertEqual(0, data.replace(b"\r\n", b"").count(b"\n"), name)
            for name in ("run_installed_or_refresh_xuunity_mcp.py", "server.py"):
                text = (claude_install / name).read_text(encoding="utf-8")
                self.assertIn('if os.name == "nt":', text, name)
                self.assertIn("subprocess.run", text, name)

    def test_refresh_python_native_fallback_syncs_without_bash(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp_dir:
            neutral_dir = Path(tmp_dir) / "neutral"

            sys.path.insert(0, str(repo_root))
            try:
                import run_installed_or_refresh_xuunity_mcp as refresh_module
            finally:
                sys.path.remove(str(repo_root))

            env_backup = {
                key: os.environ.get(key)
                for key in ("XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET", "XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR")
            }
            try:
                synced = refresh_module.refresh_via_native_launcher(repo_root, neutral_dir)
            finally:
                for key, value in env_backup.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

            self.assertTrue(synced)
            self.assertTrue((neutral_dir / "server.py").is_file())
            self.assertTrue((neutral_dir / "run.sh").is_file())
            self.assertTrue((neutral_dir / "run.cmd").is_file())
            self.assertTrue((neutral_dir / "run.ps1").is_file())
            self.assertTrue((neutral_dir / "server_core.py").is_file())

    def test_init_warns_on_existing_windows_bash_codex_config_without_duplicate(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        init_script = repo_root / "init_xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            codex_home = temp_root / "codex-home"
            codex_home.mkdir(parents=True)
            config_path = codex_home / "config.toml"
            existing_config = (
                "[mcp_servers.xuunity_light_unity]\n"
                'command = "bash"\n'
                'args = ["-lc", "exec \\"/tmp/xuunity/run_installed_or_refresh_xuunity_mcp.sh\\""]\n'
                "required = false\n"
            )
            config_path.write_text(existing_config, encoding="utf-8")

            env = self.make_env()
            env["CODEX_HOME"] = str(codex_home)
            env["CODEX_TOOLS_HOME"] = str(temp_root / "codex-tools")
            env["CLAUDE_TOOLS_HOME"] = str(temp_root / "claude-tools")
            env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(temp_root / "neutral")
            env["OS"] = "Windows_NT"
            env["APPDATA"] = str(temp_root / "AppData" / "Roaming")
            env["USERPROFILE"] = str(temp_root)

            completed = run_with_timeout(
                [resolve_bash_executable(), init_script.as_posix(), "--target", "codex", "--install-codex-config"],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(existing_config, config_path.read_text(encoding="utf-8"))
            self.assertIn("windows_codex_launcher_mismatch", completed.stderr)
            self.assertIn('command = "cmd.exe"', completed.stderr)
            self.assertIn("run_installed_or_refresh_xuunity_mcp.cmd", completed.stderr)

    def test_refresh_shell_launcher_stays_thin(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        launcher = repo_root / "run_installed_or_refresh_xuunity_mcp.sh"
        text = launcher.read_text(encoding="utf-8")

        self.assertLessEqual(len(text.splitlines()), 30)
        self.assertIn("run_installed_or_refresh_xuunity_mcp.py", text)
        self.assertNotIn("SERVER_INFO", text)
        self.assertNotIn("package.json", text)
        self.assertNotIn("init_xuunity_light_unity_mcp.sh --target", text)

    def test_installed_refresh_launcher_uses_source_root_marker_to_update_neutral_server(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        init_script = repo_root / "init_xuunity_light_unity_mcp.sh"
        package_json = repo_root / "packages" / "com.xuunity.light-mcp" / "package.json"
        package_version = json.loads(package_json.read_text(encoding="utf-8"))["version"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            codex_tools = temp_root / "codex-tools"
            claude_tools = temp_root / "claude-tools"
            neutral_dir = temp_root / "neutral"

            env = self.make_env()
            env["CODEX_TOOLS_HOME"] = str(codex_tools)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)
            env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(neutral_dir)

            completed = run_with_timeout(
                [resolve_bash_executable(), init_script.as_posix(), "--target", "neutral"],
                env=env,
                timeout_seconds=120,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)

            server_path = neutral_dir / "server.py"
            server_path.write_text("SERVER_INFO = {'name': 'xuunity-mcp', 'version': '0.0.1'}\n", encoding="utf-8")

            completed = run_with_timeout(
                [resolve_bash_executable(), (neutral_dir / "run_installed_or_refresh_xuunity_mcp.sh").as_posix(), "--print-server"],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(server_path.resolve(), Path(completed.stdout.strip()).resolve())
            tree = ast.parse(server_path.read_text(encoding="utf-8"))
            refreshed_version = ""
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "SERVER_INFO":
                            refreshed_version = str(ast.literal_eval(node.value).get("version") or "")
            self.assertEqual(package_version, refreshed_version)

    def test_explicit_install_target_can_force_claude_from_codex_context(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = self.create_fake_project(temp_root / "FakeProject")
            codex_tools = temp_root / "codex-tools"
            claude_tools = temp_root / "claude-tools"

            env = self.make_env()
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SERVER", None)
            env["XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET"] = "claude"
            env["CODEX_TOOLS_HOME"] = str(codex_tools)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)
            env["CODEX_SHELL"] = "1"

            completed = run_with_timeout(
                self.get_wrapper_cmd(wrapper) + ["server-help"],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue((claude_tools / "xuunity-mcp" / "server.py").is_file())
            self.assertFalse((codex_tools / "xuunity-mcp" / "server.py").exists())

    def test_auto_install_target_preserves_existing_claude_helper_outside_codex_context(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = self.create_fake_project(temp_root / "FakeProject")
            codex_tools = temp_root / "codex-tools"
            claude_tools = temp_root / "claude-tools"
            claude_install = claude_tools / "xuunity-mcp"
            claude_install.mkdir(parents=True)
            claude_server = claude_install / "server.py"
            claude_server.write_text("# stale claude helper\n", encoding="utf-8")

            env = self.make_env()
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_SERVER", None)
            env.pop("XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET", None)
            for key in list(env):
                if key.startswith("CODEX"):
                    env.pop(key, None)
            env.pop("CLAUDE_CODE", None)
            env.pop("CLAUDECODE", None)
            env.pop("CLAUDE_CONFIG_PATH", None)
            env["CODEX_TOOLS_HOME"] = str(codex_tools)
            env["CLAUDE_TOOLS_HOME"] = str(claude_tools)

            completed = run_with_timeout(
                self.get_wrapper_cmd(wrapper) + ["server-help"],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(claude_server.is_file())
            self.assertNotEqual("# stale claude helper\n", claude_server.read_text(encoding="utf-8"))
            self.assertFalse((codex_tools / "xuunity-mcp" / "server.py").exists())

    def test_prodmode_pins_package_version_release_tag_not_raw_commit(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        wrapper = repo_root / "xuunity_light_unity_mcp.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            source_root = temp_root / "Source"
            package_root = source_root / "packages" / "com.xuunity.light-mcp"
            templates_root = source_root / "templates"
            package_version = "0.3.14"
            release_tag = f"v{package_version}"

            templates_root.mkdir(parents=True)
            package_root.mkdir(parents=True)
            (templates_root / "server.py").write_text("# fake server\n", encoding="utf-8")
            (templates_root / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            (templates_root / "xuunity_light_unity_mcp_runtime_defaults.json").write_text("{}\n", encoding="utf-8")
            (package_root / "package.json").write_text(
                json.dumps(
                    {
                        "name": "com.xuunity.light-mcp",
                        "version": package_version,
                        "unity": "2021.3",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            remote_root = temp_root / "remote.git"
            self.run_git(temp_root, "init", "--bare", str(remote_root))
            self.run_git(source_root, "init")
            self.run_git(source_root, "config", "user.email", "test@example.invalid")
            self.run_git(source_root, "config", "user.name", "Wrapper Test")
            self.run_git(source_root, "add", ".")
            self.run_git(source_root, "commit", "-m", "Release source")
            self.run_git(source_root, "tag", "-a", release_tag, "-m", "Release")
            self.run_git(source_root, "remote", "add", "origin", str(remote_root))
            self.run_git(source_root, "push", "origin", "HEAD:refs/heads/master", f"refs/tags/{release_tag}")

            project_root = self.create_fake_project(temp_root / "FakeProject", "6000.0.58f2")
            (project_root / "Packages" / "packages-lock.json").write_text(
                json.dumps({"dependencies": {"com.xuunity.light-mcp": {"version": "old"}}}, indent=2) + "\n",
                encoding="utf-8",
            )

            env = self.make_env()
            env["XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT"] = str(source_root)
            env["CODEX_TOOLS_HOME"] = str(temp_root / "codex-tools")
            env["CLAUDE_TOOLS_HOME"] = str(temp_root / "claude-tools")

            completed = run_with_timeout(
                self.get_wrapper_cmd(wrapper) + ["prodmode", "--project-root", str(project_root)],
                env=env,
                timeout_seconds=120,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            manifest = json.loads((project_root / "Packages" / "manifest.json").read_text(encoding="utf-8"))
            dependency = manifest["dependencies"]["com.xuunity.light-mcp"]
            self.assertTrue(dependency.endswith(f"#{release_tag}"))
            self.assertNotRegex(dependency, r"#[0-9a-f]{40}$")
            self.assertIn(f"source_release_tag={release_tag}", completed.stdout)
            self.assertIn("source_head_matches_release=true", completed.stdout)

            lock = json.loads((project_root / "Packages" / "packages-lock.json").read_text(encoding="utf-8"))
            self.assertNotIn("com.xuunity.light-mcp", lock["dependencies"])


if __name__ == "__main__":
    unittest.main()
