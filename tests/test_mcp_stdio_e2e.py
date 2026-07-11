"""End-to-end MCP stdio smoke through the real launcher process.

First executable coverage for the stdio loop (templates/server_mcp_protocol.py
serve_stdio): before this file it had zero test references on any OS. The
launcher flavor matches the host — bash + .sh on POSIX, cmd.exe + .cmd on
Windows — so the Windows CI leg exercises the exact process chain colleagues
run, including wrapper exit-code propagation. No Unity is required: the
exercised tool (xuunity_setup_plan) is editor-free, and the ensure-ready case
asserts the fail-fast path when no Unity is installed at all.
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from bash_support import resolve_bash_executable, run_with_timeout, skip_if_prior_subprocess_timeout

REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_SH = REPO_ROOT / "xuunity_light_unity_mcp.sh"
WRAPPER_CMD = REPO_ROOT / "xuunity_light_unity_mcp.cmd"
PROTOCOL_VERSION = "2025-06-18"


def launcher_argv(extra_args: list | None = None) -> list:
    args = list(extra_args or [])
    if os.name == "nt":
        return ["cmd.exe", "/d", "/c", str(WRAPPER_CMD), *args]
    return [resolve_bash_executable(), WRAPPER_SH.as_posix(), *args]


def scaffold_unity_project(root: Path, *, declare_light_mcp: bool = False) -> Path:
    (root / "Assets").mkdir(parents=True)
    (root / "Packages").mkdir(parents=True)
    (root / "ProjectSettings").mkdir(parents=True)
    dependencies = {}
    if declare_light_mcp:
        dependencies["com.xuunity.light-mcp"] = (
            "https://github.com/FoxsterDev/xuunity-mcp.git?path=packages/com.xuunity.light-mcp#v0.3.42"
        )
    (root / "Packages" / "manifest.json").write_text(
        json.dumps({"dependencies": dependencies}, indent=2) + "\n", encoding="utf-8"
    )
    (root / "ProjectSettings" / "ProjectVersion.txt").write_text(
        "m_EditorVersion: 2021.3.58f1\n", encoding="utf-8"
    )
    return root


def make_launcher_env(install_dir: Path) -> dict:
    env = dict(os.environ)
    env["PYTHON"] = sys.executable
    env["PYTHONUTF8"] = "1"
    env["XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET"] = "neutral"
    env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = str(install_dir)
    for key in (
        "XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT",
        "XUUNITY_LIGHT_UNITY_MCP_SERVER",
        "XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME",
        "XUUNITY_UNITY_EDITOR_ROOTS",
    ):
        env.pop(key, None)
    return env


def mcp_request(request_id, method: str, params: dict | None = None) -> dict:
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def mcp_notification(method: str) -> dict:
    return {"jsonrpc": "2.0", "method": method}


def encode_stdin(messages: list) -> str:
    lines = []
    for message in messages:
        if isinstance(message, str):
            lines.append(message + "\n")
        else:
            lines.append(json.dumps(message, ensure_ascii=False) + "\n")
    return "".join(lines)


class McpStdioEndToEndTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)

    def run_stdio_session(self, messages: list, env: dict, timeout_seconds: int = 240):
        completed = run_with_timeout(
            launcher_argv(),
            cwd=str(REPO_ROOT),
            env=env,
            timeout_seconds=timeout_seconds,
            input_text=encode_stdin(messages),
        )
        responses = {}
        for line in completed.stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            payload = json.loads(line)
            responses[payload.get("id")] = payload
        return completed, responses

    def assert_stdout_is_ascii_json_lines(self, completed) -> None:
        for line in completed.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            self.assertTrue(
                line.isascii(),
                f"stdio frame must stay ASCII (ensure_ascii=True contract): {line[:200]}",
            )

    def test_initialize_tools_list_and_tool_call_through_real_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = scaffold_unity_project(temp_root / "Fake Project")
            env = make_launcher_env(temp_root / "neutral-install")

            completed, responses = self.run_stdio_session(
                [
                    mcp_request(1, "initialize", {"protocolVersion": PROTOCOL_VERSION}),
                    mcp_notification("notifications/initialized"),
                    mcp_request(2, "tools/list"),
                    mcp_request(
                        3,
                        "tools/call",
                        {
                            "name": "xuunity_setup_plan",
                            "arguments": {"projectRoots": [str(project_root)]},
                        },
                    ),
                    mcp_request(4, "ping"),
                ],
                env,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assert_stdout_is_ascii_json_lines(completed)

            initialize_result = responses[1]["result"]
            self.assertEqual(PROTOCOL_VERSION, initialize_result["protocolVersion"])
            self.assertEqual("xuunity-mcp", initialize_result["serverInfo"]["name"])
            self.assertIn("tools", initialize_result["capabilities"])

            tools = responses[2]["result"]["tools"]
            tool_names = {tool["name"] for tool in tools}
            self.assertIn("xuunity_setup_plan", tool_names)
            self.assertIn("unity_status", tool_names)
            for tool in tools:
                self.assertIn("inputSchema", tool, tool["name"])

            call_result = responses[3]["result"]
            self.assertFalse(call_result.get("isError"), call_result)
            plan = json.loads(call_result["content"][0]["text"])
            self.assertEqual("setup_plan", plan["action"])
            self.assertEqual([str(project_root.resolve())], plan["requested_project_roots"])

            self.assertEqual({}, responses[4]["result"])

    def test_cyrillic_and_spaces_project_root_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = scaffold_unity_project(
                temp_root / "Юнити Проекты" / "Тестовый Проект"
            )
            env = make_launcher_env(temp_root / "neutral-install")

            completed, responses = self.run_stdio_session(
                [
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
                ],
                env,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assert_stdout_is_ascii_json_lines(completed)

            call_result = responses[2]["result"]
            self.assertFalse(call_result.get("isError"), call_result)
            plan = json.loads(call_result["content"][0]["text"])
            self.assertEqual(
                [str(project_root.resolve())],
                plan["requested_project_roots"],
                "non-ASCII project path must round-trip intact through the stdio frame",
            )

    def test_protocol_errors_are_reported_without_killing_the_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            env = make_launcher_env(temp_root / "neutral-install")

            completed, responses = self.run_stdio_session(
                [
                    mcp_request(1, "initialize", {"protocolVersion": PROTOCOL_VERSION}),
                    mcp_notification("notifications/initialized"),
                    mcp_request(7, "definitely/not-a-method"),
                    "this line is not json",
                    mcp_request(9, "ping"),
                ],
                env,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(-32601, responses[7]["error"]["code"])
            self.assertEqual(-32700, responses[None]["error"]["code"])
            self.assertEqual({}, responses[9]["result"], "session must survive bad frames")

    def test_empty_stdin_exits_zero_through_wrapper_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            env = make_launcher_env(temp_root / "neutral-install")

            completed = run_with_timeout(
                launcher_argv(),
                cwd=str(REPO_ROOT),
                env=env,
                timeout_seconds=240,
                input_text="",
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("", completed.stdout.strip())


class EnsureReadyFastFailWithoutUnityTest(unittest.TestCase):
    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)

    def test_ensure_ready_fails_fast_when_no_unity_is_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = scaffold_unity_project(
                temp_root / "Fake Project", declare_light_mcp=True
            )
            empty_editor_root = temp_root / "no-editors-here"
            empty_editor_root.mkdir()

            env = make_launcher_env(temp_root / "neutral-install")
            env["XUUNITY_UNITY_EDITOR_ROOTS"] = str(empty_editor_root)

            started = time.monotonic()
            completed = run_with_timeout(
                launcher_argv(
                    ["ensure-ready", "--project-root", str(project_root), "--open-editor"]
                ),
                cwd=str(REPO_ROOT),
                env=env,
                timeout_seconds=120,
            )
            elapsed_seconds = time.monotonic() - started

            combined = completed.stdout + completed.stderr
            self.assertNotEqual(0, completed.returncode, combined)
            self.assertIn("unity_app_not_found", combined)
            self.assertIn(
                str(empty_editor_root),
                combined,
                "error must list the searched roots so the fix is actionable",
            )
            self.assertLess(
                elapsed_seconds,
                30.0,
                "no-Unity ensure-ready must fail fast, not burn the 120 s heartbeat wait",
            )


if __name__ == "__main__":
    unittest.main()
