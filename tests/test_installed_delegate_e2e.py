"""Config-to-connection: the artifacts colleagues actually run, end to end.

The stdio e2e in test_mcp_stdio_e2e.py drives the REPO copy of the launcher.
Real client sessions run something else: the refresh launcher installs a copy
of the helper into an install dir, client configs point at that installed
copy, and every MCP session starts from whatever the config says. None of
that path had executable coverage. These tests close it:

- the refresh launcher (``run_installed_or_refresh_xuunity_mcp.{cmd,sh}``)
  performs a real install into a sandboxed neutral dir and then serves an MCP
  stdio session from the INSTALLED delegate — the exact process chain a
  client spawn goes through;
- ``init_xuunity_light_unity_mcp.sh --install-claude-config`` writes a client
  config into a sandboxed path, and the test spawns *exactly the command
  written into that config* and requires MCP ``initialize`` to answer. This
  kills the historical class where the registered command pointed at a
  launcher flavor that could not start on the host.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from bash_support import (
    resolve_bash_executable,
    run_with_timeout,
    skip_if_prior_subprocess_timeout,
)
from test_mcp_stdio_e2e import (
    PROTOCOL_VERSION,
    encode_stdin,
    make_launcher_env,
    mcp_notification,
    mcp_request,
    scaffold_unity_project,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REFRESH_CMD = REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.cmd"
REFRESH_SH = REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.sh"
INSTALLER_SH = REPO_ROOT / "init_xuunity_light_unity_mcp.sh"

INSTALLED_ARTIFACTS = (
    "server.py",
    "run.sh",
    "run.cmd",
    "run.ps1",
    "run_installed_or_refresh_xuunity_mcp.sh",
    "run_installed_or_refresh_xuunity_mcp.py",
    "run_installed_or_refresh_xuunity_mcp.cmd",
    ".source_root",
)


def refresh_launcher_argv() -> list:
    if os.name == "nt":
        return ["cmd.exe", "/d", "/c", str(REFRESH_CMD)]
    return [resolve_bash_executable(), REFRESH_SH.as_posix()]


def parse_responses(stdout: str) -> dict:
    responses = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            payload = json.loads(line)
            responses[payload.get("id")] = payload
    return responses


def assert_mcp_session_answers(test: unittest.TestCase, completed, project_root: Path) -> dict:
    test.assertEqual(0, completed.returncode, completed.stderr)
    responses = parse_responses(completed.stdout)

    initialize_result = responses[1]["result"]
    test.assertEqual("xuunity-mcp", initialize_result["serverInfo"]["name"])

    call_result = responses[2]["result"]
    test.assertFalse(call_result.get("isError"), call_result)
    plan = json.loads(call_result["content"][0]["text"])
    test.assertEqual("setup_plan", plan["action"])
    test.assertEqual([str(project_root.resolve())], plan["requested_project_roots"])
    return responses


def standard_session_messages(project_root: Path) -> list:
    return [
        mcp_request(1, "initialize", {"protocolVersion": PROTOCOL_VERSION}),
        mcp_notification("notifications/initialized"),
        mcp_request(
            2,
            "tools/call",
            {
                "name": "xuunity_setup_plan",
                "arguments": {"projectRoots": [str(project_root)]},
            },
        ),
    ]


class InstalledDelegateStdioTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)

    def test_refresh_launcher_installs_then_serves_mcp_from_installed_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            install_dir = temp_root / "neutral-install"
            project_root = scaffold_unity_project(temp_root / "Fake Project")
            env = make_launcher_env(install_dir)

            completed = run_with_timeout(
                refresh_launcher_argv(),
                cwd=str(REPO_ROOT),
                env=env,
                timeout_seconds=300,
                input_text=encode_stdin(standard_session_messages(project_root)),
            )

            assert_mcp_session_answers(self, completed, project_root)

            for artifact in INSTALLED_ARTIFACTS:
                self.assertTrue(
                    (install_dir / artifact).is_file(),
                    f"refresh must install {artifact} into the neutral dir",
                )
            marker_line = (
                (install_dir / ".source_root").read_text(encoding="utf-8").splitlines()[0].strip()
            )
            self.assertEqual(
                REPO_ROOT.resolve(),
                Path(marker_line).resolve(),
                "installed copy must point back at this source checkout",
            )


class ClaudeConfigToConnectionTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)
        try:
            self.bash_executable = resolve_bash_executable()
        except Exception as exc:  # pragma: no cover - host without bash
            self.skipTest(f"bash unavailable on this host: {exc}")

    def build_installer_env(self, temp_root: Path, install_dir: Path) -> dict:
        env = make_launcher_env(install_dir)
        env["CLAUDE_CONFIG_PATH"] = str(temp_root / "claude-config" / "claude.json")
        env["CODEX_HOME"] = str(temp_root / "codex-home")
        env["CODEX_TOOLS_HOME"] = str(temp_root / "codex-tools")
        env["CLAUDE_TOOLS_HOME"] = str(temp_root / "claude-tools")
        return env

    def test_command_written_into_claude_config_starts_a_working_mcp_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            install_dir = temp_root / "neutral-install"
            project_root = scaffold_unity_project(temp_root / "Fake Project")
            env = self.build_installer_env(temp_root, install_dir)

            installer = run_with_timeout(
                [
                    self.bash_executable,
                    INSTALLER_SH.as_posix(),
                    "--target",
                    "neutral",
                    "--install-claude-config",
                ],
                cwd=str(REPO_ROOT),
                env=env,
                timeout_seconds=420,
            )
            self.assertEqual(0, installer.returncode, installer.stdout + installer.stderr)

            config_path = Path(env["CLAUDE_CONFIG_PATH"])
            self.assertTrue(config_path.is_file(), "installer must write the Claude config")
            config = json.loads(config_path.read_text(encoding="utf-8"))
            server_entry = config["mcpServers"]["xuunity_light_unity"]
            self.assertEqual("stdio", server_entry["type"], server_entry)

            configured_argv = [server_entry["command"], *server_entry["args"]]
            if os.name == "nt":
                self.assertEqual("cmd.exe", server_entry["command"], server_entry)
                self.assertIn(
                    "XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR",
                    " ".join(server_entry["args"]),
                    "neutral-target Windows config must resolve the install dir via env",
                )
            else:
                self.assertEqual("bash", server_entry["command"], server_entry)

            completed = run_with_timeout(
                configured_argv,
                cwd=str(temp_root),
                env=env,
                timeout_seconds=300,
                input_text=encode_stdin(standard_session_messages(project_root)),
            )

            assert_mcp_session_answers(self, completed, project_root)


if __name__ == "__main__":
    unittest.main()
