"""Hostile console codepages, live through the real Windows launcher chain.

Wall #3 of the Windows deep review: piped stdio on Windows defaults to the
ANSI/OEM codepage, so a Cyrillic project path used to kill serve_stdio
mid-decode and ``print_json(ensure_ascii=False)`` raised UnicodeEncodeError
on RU consoles. The fix is host-wide UTF-8 (PYTHONUTF8 + stdio reconfigure);
until now it was pinned by unit tests only. These tests re-create the hostile
environment for the whole ``cmd.exe → .cmd → python → server`` chain via
``PYTHONIOENCODING=<codepage>:strict``, which outranks UTF-8 mode for stdio
and therefore fails loudly if the reconfigure ever regresses:

- ``cp866`` is the RU OEM console;
- ``cp1252`` is the Western ANSI codepage, where Cyrillic output cannot be
  encoded at all — the classic mixed-locale crash.
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

from bash_support import run_with_timeout, skip_if_prior_subprocess_timeout
from test_mcp_stdio_e2e import (
    PROTOCOL_VERSION,
    encode_stdin,
    launcher_argv,
    make_launcher_env,
    mcp_notification,
    mcp_request,
    scaffold_unity_project,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
HOSTILE_CODEPAGES = ("cp866", "cp1252")


def hostile_env(install_dir: Path, codepage: str) -> dict:
    env = make_launcher_env(install_dir)
    env["PYTHONIOENCODING"] = f"{codepage}:strict"
    return env


def assert_no_encoding_crash(test: unittest.TestCase, completed) -> None:
    combined = completed.stdout + completed.stderr
    test.assertNotIn("UnicodeEncodeError", combined, combined[-2000:])
    test.assertNotIn("UnicodeDecodeError", combined, combined[-2000:])


@unittest.skipUnless(os.name == "nt", "native Windows console-codepage behavior")
class HostileConsoleCodepageTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)

    def test_cli_setup_plan_with_cyrillic_path_survives_hostile_codepages(self) -> None:
        for codepage in HOSTILE_CODEPAGES:
            with self.subTest(codepage=codepage), tempfile.TemporaryDirectory() as tmp_dir:
                temp_root = Path(tmp_dir)
                project_root = scaffold_unity_project(
                    temp_root / "Юнити Проекты" / "Тестовый Проект"
                )
                env = hostile_env(temp_root / "neutral-install", codepage)

                completed = run_with_timeout(
                    launcher_argv(["setup-plan", "--project-root", str(project_root)]),
                    cwd=str(REPO_ROOT),
                    env=env,
                    timeout_seconds=240,
                )

                assert_no_encoding_crash(self, completed)
                self.assertEqual(0, completed.returncode, completed.stderr)
                plan = json.loads(completed.stdout)
                self.assertEqual(
                    [str(project_root.resolve())],
                    plan.get("requested_project_roots"),
                    "Cyrillic project path must survive a hostile console codepage",
                )

    def test_mcp_stdio_roundtrip_survives_cp866_stdin_and_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = scaffold_unity_project(
                temp_root / "Юнити Проекты" / "Тестовый Проект"
            )
            env = hostile_env(temp_root / "neutral-install", "cp866")

            completed = run_with_timeout(
                launcher_argv(),
                cwd=str(REPO_ROOT),
                env=env,
                timeout_seconds=240,
                input_text=encode_stdin(
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
                    ]
                ),
            )

            assert_no_encoding_crash(self, completed)
            self.assertEqual(0, completed.returncode, completed.stderr)
            responses = {}
            for line in completed.stdout.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    payload = json.loads(line)
                    responses[payload.get("id")] = payload

            call_result = responses[2]["result"]
            self.assertFalse(call_result.get("isError"), call_result)
            plan = json.loads(call_result["content"][0]["text"])
            self.assertEqual(
                [str(project_root.resolve())],
                plan["requested_project_roots"],
                "UTF-8 stdin frames must decode correctly despite a cp866 stdio default",
            )

    def test_ensure_ready_error_path_stays_clean_under_cp866(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = scaffold_unity_project(
                temp_root / "Юнити Проекты" / "Тестовый Проект", declare_light_mcp=True
            )
            empty_editor_root = temp_root / "no-editors-here"
            empty_editor_root.mkdir()

            env = hostile_env(temp_root / "neutral-install", "cp866")
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

            assert_no_encoding_crash(self, completed)
            combined = completed.stdout + completed.stderr
            self.assertNotEqual(0, completed.returncode, combined)
            self.assertIn("unity_app_not_found", combined)
            self.assertLess(elapsed_seconds, 30.0, "fail-fast must survive the RU codepage leg")


if __name__ == "__main__":
    unittest.main()
