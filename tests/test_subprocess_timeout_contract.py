"""Helper-subprocess hang and console-flash contract.

Every helper spawn (tasklist, taskkill, PowerShell listing, ps, lsof, wslpath,
git, refresh) must carry a timeout: a hung probe otherwise blocks the MCP
server forever with no diagnostic. Long-lived child processes that ARE the
server (delegated run, batch self-invocations) are allowlisted. Windows-facing
helpers must also request CREATE_NO_WINDOW so GUI-hosted servers do not flash
console windows.
"""

import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_core
import server_editor_host
import server_editor_host_lifecycle
from server_host_platform import HostPlatformAdapter

REPO_ROOT = Path(__file__).resolve().parents[1]
SWEPT_FILES = sorted((REPO_ROOT / "templates").glob("*.py")) + [
    REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.py"
]

# (file name, enclosing function): subprocess.run calls that intentionally have
# no timeout because the child IS the workload (server run / batch lane), not a
# short helper probe.
NO_TIMEOUT_ALLOWLIST = {
    ("server_launcher.py", "exec_python_script"),
    ("server_launcher.py", "run_server_with_optional_compact_summary"),
    ("server_batch_recovery.py", "run_batch_build_config_compile_matrix_probe"),
    ("server_batch_recovery.py", "run_self_json_command_with_completed"),
    ("server_batch_recovery.py", "run_self_json_command"),
    ("run_installed_or_refresh_xuunity_mcp.py", "exec_run"),
}

HIDDEN_WINDOW_FILES = (
    "server_host_platform.py",
    "server_editor_host_lifecycle.py",
    "server_launcher.py",
    "server_workspace_effects.py",
)


def iter_subprocess_run_calls(tree: ast.AST):
    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.function_stack: list[str] = []
            self.calls: list[tuple[str, ast.Call]] = []

        def _visit_function(self, node) -> None:
            self.function_stack.append(node.name)
            self.generic_visit(node)
            self.function_stack.pop()

        visit_FunctionDef = _visit_function
        visit_AsyncFunctionDef = _visit_function

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "run"
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
            ):
                enclosing = self.function_stack[-1] if self.function_stack else "<module>"
                self.calls.append((enclosing, node))
            self.generic_visit(node)

    visitor = Visitor()
    visitor.visit(tree)
    return visitor.calls


class SubprocessTimeoutSweepTest(unittest.TestCase):
    def test_every_helper_subprocess_run_has_a_timeout(self) -> None:
        offenders: list[str] = []
        seen_any = False
        for source in SWEPT_FILES:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for enclosing, call in iter_subprocess_run_calls(tree):
                seen_any = True
                if (source.name, enclosing) in NO_TIMEOUT_ALLOWLIST:
                    continue
                has_timeout = any(
                    keyword.arg == "timeout" for keyword in call.keywords
                )
                has_kwargs_splat = any(
                    keyword.arg is None for keyword in call.keywords
                )
                if not has_timeout and not (
                    has_kwargs_splat and enclosing == "<module>"
                ):
                    offenders.append(f"{source.name}:{call.lineno} in {enclosing}()")
        self.assertTrue(seen_any, "sweep found no subprocess.run calls at all")
        self.assertEqual(
            [],
            offenders,
            "subprocess.run without timeout= (add it or extend NO_TIMEOUT_ALLOWLIST)",
        )

    def test_allowlist_entries_still_exist(self) -> None:
        found: set[tuple[str, str]] = set()
        for source in SWEPT_FILES:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for enclosing, _ in iter_subprocess_run_calls(tree):
                found.add((source.name, enclosing))
        stale = NO_TIMEOUT_ALLOWLIST - found
        self.assertEqual(set(), stale, "stale allowlist entries; prune them")

    def test_windows_facing_helpers_request_hidden_windows(self) -> None:
        for name in HIDDEN_WINDOW_FILES:
            text = (REPO_ROOT / "templates" / name).read_text(encoding="utf-8")
            self.assertIn("hidden_window_subprocess_kwargs", text, name)
        refresh_text = (REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE_NO_WINDOW", refresh_text)


class HiddenWindowKwargsTest(unittest.TestCase):
    def test_posix_returns_empty_kwargs(self) -> None:
        if os.name == "nt":
            self.skipTest("posix-only expectation")
        self.assertEqual({}, server_core.hidden_window_subprocess_kwargs())

    def test_windows_like_host_requests_no_window(self) -> None:
        with mock.patch.object(os, "name", "nt"):
            kwargs = server_core.hidden_window_subprocess_kwargs()
        self.assertIn("creationflags", kwargs)
        self.assertEqual(
            getattr(subprocess, "CREATE_NO_WINDOW", 0), kwargs["creationflags"]
        )


class TaskkillContractTest(unittest.TestCase):
    def test_taskkill_kills_process_tree_with_timeout(self) -> None:
        completed = mock.Mock(returncode=0)
        # Call through the facade: it re-syncs the owner module, so leftover
        # patches from earlier facade-based tests cannot leak in here.
        with (
            mock.patch.object(sys, "platform", "win32"),
            mock.patch.object(server_editor_host, "pid_is_alive", side_effect=[True, False]),
            mock.patch.object(
                server_editor_host.subprocess, "run", return_value=completed
            ) as run_mock,
        ):
            self.assertTrue(server_editor_host.terminate_editor_pid(4242, 2000))

        run_mock.assert_called_once()
        argv = run_mock.call_args.args[0]
        self.assertEqual(["taskkill", "/F", "/T", "/PID", "4242"], argv)
        self.assertEqual(
            server_editor_host_lifecycle.TASKKILL_TIMEOUT_SECONDS,
            run_mock.call_args.kwargs["timeout"],
        )


class ProcessListingTimeoutTest(unittest.TestCase):
    def test_powershell_listing_timeout_is_reported_not_raised(self) -> None:
        adapter = HostPlatformAdapter(platform_kind="windows")
        with (
            mock.patch("server_host_platform.is_wsl", return_value=True),
            mock.patch("server_host_platform.shutil.which", return_value="powershell.exe"),
            mock.patch(
                "server_host_platform.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="powershell.exe", timeout=30),
            ),
        ):
            report = adapter.list_process_commands_report()

        self.assertFalse(report["available"])
        self.assertEqual("process_listing_timeout", report["error_code"])
        self.assertEqual([], report["commands"])

    def test_posix_ps_timeout_is_reported_not_raised(self) -> None:
        if os.name == "nt":
            self.skipTest("posix ps branch")
        adapter = HostPlatformAdapter(platform_kind="macos")
        with mock.patch(
            "server_host_platform.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ps", timeout=30),
        ):
            report = adapter.list_process_commands_report()

        self.assertFalse(report["available"])
        self.assertEqual("process_listing_timeout", report["error_code"])
        self.assertEqual([], report["commands"])


if __name__ == "__main__":
    unittest.main()
