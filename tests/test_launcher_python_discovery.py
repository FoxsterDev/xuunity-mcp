"""Interpreter discovery across launcher flavours (RG-02, fix design F-1).

A GUI-spawned client inherits a PATH whose first python3 can be 3.9. The shell launchers
stay thin and exec the first Python they find; every Python entrypoint then re-runs itself
with a supported interpreter (script venv, neutral install venv, versioned names on PATH).
"""

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
for path in (TESTS_DIR, TEMPLATES_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import server_launcher
import server_python_gate
from bash_support import resolve_bash_executable, run_with_timeout, skip_if_prior_subprocess_timeout


def write_executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


OLD_PYTHON_ENV = "XUUNITY_TEST_OLD_PYTHON"
REQUIRE_E2E_ENV = "XUUNITY_REQUIRE_LAUNCHER_E2E"
PROBE_SERVER = (
    "import sys\n"
    "print('XUUNITY_PROBE_EXECUTABLE=' + sys.executable)\n"
    "print('XUUNITY_PROBE_VERSION=%d.%d' % sys.version_info[:2])\n"
    "print('XUUNITY_PROBE_ARGS=' + ' '.join(sys.argv[1:]))\n"
)


def old_system_python() -> str:
    explicit = os.environ.get(OLD_PYTHON_ENV, "").strip()
    if explicit:
        candidates = [explicit]
    elif os.name == "nt":
        candidates = []
    else:
        candidates = ["/usr/bin/python3"]
    for candidate in candidates:
        if not os.path.isfile(candidate):
            continue
        completed = subprocess.run(
            [candidate, "-c", "import sys; print(sys.version_info[:2] < (3, 10))"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if completed.stdout.strip() == "True":
            return candidate
    return ""


def skip_or_fail_without(test: unittest.TestCase, reason: str) -> None:
    if os.environ.get(REQUIRE_E2E_ENV) == "1":
        test.fail(f"{REQUIRE_E2E_ENV}=1 but the launcher end-to-end prerequisite is missing: {reason}")
    test.skipTest(reason)


def probe_fields(stdout: str) -> dict:
    fields = {}
    for line in stdout.splitlines():
        if line.startswith("XUUNITY_PROBE_") and "=" in line:
            key, value = line.split("=", 1)
            fields[key[len("XUUNITY_PROBE_"):].lower()] = value.strip()
    return fields


def same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))


def make_venv(target: Path) -> Path:
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(target)],
        check=True,
        capture_output=True,
        timeout=180,
    )
    name = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return target / name


class PythonGateUnitTests(unittest.TestCase):
    def run_gate(self, env: dict, *, supported: set, path_names: dict, script_dirs: list):
        stderr = io.StringIO()
        execv = mock.Mock()

        def posix_exec(candidate, command):
            execv(candidate, command)
            raise SystemExit(0)

        def windows_run(command, check=False):
            execv(command[0], list(command))
            return subprocess.CompletedProcess(command, 0)

        with (
            mock.patch.object(sys, "version_info", (3, 9, 6, "final", 0)),
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(server_python_gate.shutil, "which", side_effect=lambda name: path_names.get(name)),
            mock.patch.object(server_python_gate, "interpreter_is_supported", side_effect=lambda c: c in supported),
            mock.patch.object(server_python_gate.os, "execv", side_effect=posix_exec),
            mock.patch.object(server_python_gate.subprocess, "run", side_effect=windows_run),
            contextlib.redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as raised:
                server_python_gate.ensure_supported_python("/x/entry.py", ["--help"], script_dirs)
            marker = os.environ.get(server_python_gate.REEXEC_MARKER_ENV)
        return raised.exception.code, execv, stderr.getvalue(), marker

    def test_old_path_python_reexecs_into_the_neutral_venv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            neutral = Path(tmp) / "neutral"
            venv_python = write_executable(neutral / ".venv" / "bin" / "python", "#!/bin/sh\n")
            code, execv, stderr, marker = self.run_gate(
                {"XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR": str(neutral)},
                supported={str(venv_python)},
                path_names={"python3": "/usr/bin/python3"},
                script_dirs=[Path(tmp) / "source"],
            )

        self.assertEqual(0, code)
        execv.assert_called_once_with(str(venv_python), [str(venv_python), "/x/entry.py", "--help"])
        self.assertIn("too old; re-running with", stderr)
        self.assertEqual("1", marker)

    def test_versioned_name_on_path_is_used_when_no_venv_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, execv, _, _ = self.run_gate(
                {"XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR": str(Path(tmp) / "none")},
                supported={"/opt/bin/python3.12"},
                path_names={"python3": "/usr/bin/python3", "python3.12": "/opt/bin/python3.12"},
                script_dirs=[],
            )

        self.assertEqual(0, code)
        self.assertEqual("/opt/bin/python3.12", execv.call_args.args[0])

    def test_no_supported_interpreter_lists_what_was_tried(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, execv, stderr, _ = self.run_gate(
                {"XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR": str(Path(tmp) / "none")},
                supported=set(),
                path_names={"python3": "/usr/bin/python3"},
                script_dirs=[],
            )

        self.assertEqual(1, code)
        execv.assert_not_called()
        self.assertIn("tried: /usr/bin/python3", stderr)
        self.assertIn("Set PYTHON", stderr)

    def test_explicit_python_override_is_never_silently_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            neutral = Path(tmp) / "neutral"
            venv_python = write_executable(neutral / ".venv" / "bin" / "python", "#!/bin/sh\n")
            code, execv, stderr, _ = self.run_gate(
                {"PYTHON": "/usr/bin/python3", "XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR": str(neutral)},
                supported={str(venv_python)},
                path_names={},
                script_dirs=[],
            )

        self.assertEqual(1, code)
        execv.assert_not_called()
        self.assertIn("PYTHON=/usr/bin/python3 reports 3.9.6", stderr)

    def test_a_reexecuted_interpreter_that_is_still_old_does_not_loop(self) -> None:
        code, execv, _, _ = self.run_gate(
            {server_python_gate.REEXEC_MARKER_ENV: "1"},
            supported={"/opt/bin/python3.12"},
            path_names={"python3.12": "/opt/bin/python3.12"},
            script_dirs=[],
        )

        self.assertEqual(1, code)
        execv.assert_not_called()

    def test_supported_interpreter_clears_the_marker_for_child_launchers(self) -> None:
        with mock.patch.dict(os.environ, {server_python_gate.REEXEC_MARKER_ENV: "1"}):
            server_python_gate.ensure_supported_python("/x/entry.py", [], [])
            self.assertNotIn(server_python_gate.REEXEC_MARKER_ENV, os.environ)


class InstallOwnershipTests(unittest.TestCase):
    def test_wrapper_sync_keeps_installer_delegates_and_targets_the_neutral_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            neutral = root / "neutral"
            claude_dir = root / "claude-tools" / "xuunity-mcp"
            write_executable(claude_dir / "run.sh", f'#!/usr/bin/env bash\nexec "$BASH" "{neutral}/run.sh" "$@"\n')
            env = {
                "CLAUDECODE": "1",
                "CLAUDE_TOOLS_HOME": str(root / "claude-tools"),
                "XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR": str(neutral),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                os.environ.pop("XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET", None)
                for name in ("CODEX_SHELL", "CODEX_THREAD_ID", "CODEX_SANDBOX", "CODEX_HOME", "CODEX_CI"):
                    os.environ.pop(name, None)
                delegated = server_launcher.resolve_install_dir()
                write_executable(claude_dir / "run.sh", "#!/usr/bin/env bash\n" + "echo full copy\n" * 5)
                full_copy = server_launcher.resolve_install_dir()

        self.assertEqual(str(neutral), delegated)
        self.assertEqual(str(claude_dir), full_copy)


@unittest.skipIf(os.name == "nt", "POSIX shell launcher with a real old interpreter")
class GuiPathEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)
        self.old_python = old_system_python()
        if not self.old_python:
            skip_or_fail_without(self, f"needs a python3 older than 3.10 (set {OLD_PYTHON_ENV})")

    def old_first_env(self, **extra: str) -> dict:
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHON", "XUUNITY_LIGHT_UNITY_MCP_REEXEC", "XUUNITY_LIGHT_UNITY_MCP_SERVER"}
        }
        old_dir = Path(self.old_python).parent
        shim_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, shim_dir, True)
        write_executable(shim_dir / "python3", f'#!/bin/sh\nexec "{self.old_python}" "$@"\n')
        env["PATH"] = os.pathsep.join([str(shim_dir), str(old_dir), "/usr/bin", "/bin", "/usr/sbin", "/sbin"])
        env.update(extra)
        return env

    def test_run_sh_with_an_old_explicit_python_refuses_instead_of_running(self) -> None:
        completed = run_with_timeout(
            [resolve_bash_executable(), (TEMPLATES_DIR / "run.sh").as_posix(), "--help"],
            env=self.old_first_env(PYTHON=self.old_python),
            timeout_seconds=120,
        )

        self.assertNotEqual(0, completed.returncode, completed.stdout)
        self.assertIn("Python 3.10 or newer is required", completed.stderr)
        self.assertIn("Set PYTHON", completed.stderr)

    def test_server_py_under_an_old_python3_reexecs_into_the_neutral_venv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            venv_python = make_venv(Path(tmp) / "neutral" / ".venv")
            completed = run_with_timeout(
                [self.old_python, (TEMPLATES_DIR / "server.py").as_posix(), "--help"],
                env=self.old_first_env(XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR=str(Path(tmp) / "neutral")),
                timeout_seconds=120,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("usage:", completed.stdout.lower())
        self.assertIn("too old; re-running with", completed.stderr)
        self.assertIn(str(venv_python), completed.stderr)

    def test_wrapper_answers_help_under_a_gui_path_with_an_old_python3_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            neutral = root / "neutral"
            write_executable(
                neutral / ".venv" / "bin" / "python",
                f'#!/bin/sh\nexec "{sys.executable}" "$@"\n',
            )
            env = {
                key: value
                for key, value in os.environ.items()
                if key not in {"PYTHON", "XUUNITY_LIGHT_UNITY_MCP_REEXEC"}
            }
            env = self.old_first_env(XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR=str(neutral))
            completed = run_with_timeout(
                [resolve_bash_executable(), (REPO_ROOT / "xuunity_light_unity_mcp.sh").as_posix(), "--help"],
                env=env,
                timeout_seconds=120,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("Usage:", completed.stdout)
        self.assertIn("too old; re-running with", completed.stderr)


class LauncherFlavourParityTests(unittest.TestCase):
    SHELL = (
        REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.sh",
        REPO_ROOT / "xuunity_light_unity_mcp.sh",
        TEMPLATES_DIR / "run.sh",
    )
    NATIVE = (
        REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.cmd",
        REPO_ROOT / "xuunity_light_unity_mcp.cmd",
        TEMPLATES_DIR / "run.cmd",
        REPO_ROOT / "xuunity_light_unity_mcp.ps1",
        TEMPLATES_DIR / "run.ps1",
    )
    PYTHON_ENTRYPOINTS = (
        REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.py",
        TEMPLATES_DIR / "server_launcher.py",
        TEMPLATES_DIR / "server.py",
    )

    ORDER_MARKERS = {
        ".sh": ('[[ -n "${PYTHON:-}" ]]', "/.venv/", "command -v python3"),
        ".cmd": ("if not defined PYTHON", ":xuunity_try_neutral_venv", ":xuunity_try_py"),
        ".ps1": ("$env:PYTHON", "$neutralDir \".venv", "Get-Command $name"),
    }

    def test_explicit_python_comes_before_any_venv_or_path_candidate(self) -> None:
        for launcher in (*self.SHELL, *self.NATIVE):
            text = launcher.read_text(encoding="utf-8")
            markers = self.ORDER_MARKERS[launcher.suffix]
            if launcher.name == "xuunity_light_unity_mcp.sh":
                markers = (markers[0], markers[2])
            with self.subTest(launcher=launcher.name):
                positions = [text.find(marker) for marker in markers]
                self.assertNotIn(-1, positions, markers)
                self.assertEqual(sorted(positions), positions)

    def test_native_flavours_probe_the_version_and_know_the_neutral_venv(self) -> None:
        for launcher in self.NATIVE:
            text = launcher.read_text(encoding="utf-8")
            with self.subTest(launcher=launcher.name):
                self.assertRegex(text, r"sys\.version_info >= \(3, 10\)")
                self.assertIn("XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR", text)
                self.assertIn("xuunity-mcp", text)

    def test_shell_flavours_stay_thin_and_python_entrypoints_own_the_gate(self) -> None:
        for launcher in self.SHELL:
            text = launcher.read_text(encoding="utf-8")
            with self.subTest(launcher=launcher.name):
                self.assertLessEqual(len(text.splitlines()), 40)
                self.assertNotIn("version_info", text)
        for entrypoint in self.PYTHON_ENTRYPOINTS:
            with self.subTest(entrypoint=entrypoint.name):
                self.assertIn("ensure_supported_python", entrypoint.read_text(encoding="utf-8"))

    def test_entrypoints_parse_on_old_interpreters(self) -> None:
        old = old_system_python()
        if not old:
            skip_or_fail_without(self, f"needs a python3 older than 3.10 (set {OLD_PYTHON_ENV})")
        for entrypoint in (*self.PYTHON_ENTRYPOINTS, TEMPLATES_DIR / "server_python_gate.py"):
            completed = subprocess.run(
                [old, "-c", "import ast, sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())", str(entrypoint)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, f"{entrypoint.name}: {completed.stderr}")



@unittest.skipUnless(os.name == "nt", "native Windows launchers")
class WindowsNativeLauncherEndToEndTests(unittest.TestCase):
    FLAVOURS = ("cmd", "ps1")

    def setUp(self) -> None:
        self.old_python = old_system_python()
        if not self.old_python:
            skip_or_fail_without(self, f"set {OLD_PYTHON_ENV} to a Python older than 3.10")
        self.pwsh = shutil.which("pwsh") or shutil.which("powershell")
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.probe = self.root / "probe.py"
        self.probe.write_text(PROBE_SERVER, encoding="utf-8")
        self.neutral = self.root / "neutral"

    def env(self, **extra: str) -> dict:
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() not in {"PYTHON", "XUUNITY_LIGHT_UNITY_MCP_REEXEC", "XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"}
        }
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        env["PATH"] = os.pathsep.join(
            [
                str(Path(self.old_python).parent),
                str(Path(system_root) / "System32"),
                system_root,
                str(Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0"),
            ]
        )
        env["XUUNITY_LIGHT_UNITY_MCP_SERVER"] = str(self.probe)
        env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(self.neutral)
        env.update(extra)
        return env

    def launch(self, flavour: str, env: dict) -> subprocess.CompletedProcess:
        if flavour == "cmd":
            command = [os.environ.get("ComSpec", "cmd.exe"), "/d", "/c", str(TEMPLATES_DIR / "run.cmd"), "probe-arg"]
        else:
            if not self.pwsh:
                skip_or_fail_without(self, "no pwsh or powershell on PATH")
            command = [self.pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TEMPLATES_DIR / "run.ps1"), "probe-arg"]
        return run_with_timeout(command, env=env, timeout_seconds=120)

    def test_an_old_explicit_python_is_refused(self) -> None:
        for flavour in self.FLAVOURS:
            with self.subTest(flavour=flavour):
                completed = self.launch(flavour, self.env(PYTHON=self.old_python))

                self.assertNotEqual(0, completed.returncode, completed.stdout)
                self.assertNotIn("XUUNITY_PROBE_EXECUTABLE", completed.stdout)
                self.assertIn("not a working Python 3.10+", completed.stdout + completed.stderr)

    def test_the_neutral_venv_wins_over_an_old_python_first_on_path(self) -> None:
        venv_python = make_venv(self.neutral / ".venv")
        for flavour in self.FLAVOURS:
            with self.subTest(flavour=flavour):
                completed = self.launch(flavour, self.env())

                self.assertEqual(0, completed.returncode, completed.stderr)
                fields = probe_fields(completed.stdout)
                self.assertTrue(same_path(str(venv_python), fields.get("executable", "")), completed.stdout)
                self.assertEqual("probe-arg", fields.get("args"))

    def test_without_a_venv_the_old_python_first_on_path_is_never_used(self) -> None:
        for flavour in self.FLAVOURS:
            with self.subTest(flavour=flavour):
                completed = self.launch(flavour, self.env())

                fields = probe_fields(completed.stdout)
                if completed.returncode == 0:
                    self.assertFalse(same_path(self.old_python, fields.get("executable", "")), completed.stdout)
                    major, minor = (int(part) for part in fields["version"].split("."))
                    self.assertGreaterEqual((major, minor), (3, 10))
                else:
                    self.assertNotIn("XUUNITY_PROBE_EXECUTABLE", completed.stdout)
                    self.assertIn("Python 3.10 or newer was not found", completed.stdout + completed.stderr)

    def test_server_py_under_the_old_python_reexecs_into_the_neutral_venv(self) -> None:
        venv_python = make_venv(self.neutral / ".venv")
        env = self.env()
        env.pop("XUUNITY_LIGHT_UNITY_MCP_SERVER", None)
        completed = run_with_timeout(
            [self.old_python, str(TEMPLATES_DIR / "server.py"), "--help"],
            env=env,
            timeout_seconds=120,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("usage:", completed.stdout.lower())
        self.assertIn("too old; re-running with", completed.stderr)
        self.assertIn(os.path.normcase(str(venv_python)), os.path.normcase(completed.stderr))


if __name__ == "__main__":
    unittest.main()
