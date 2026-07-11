"""Windows .cmd launcher contract.

Guards the fixes for the fresh-Windows setup wall:
- parse-time `exit /b %ERRORLEVEL%` inside parenthesized blocks made every
  wrapper exit 0 regardless of failure;
- `where python` accepted the Microsoft Store stub, which cannot run scripts;
- no Python >=3.10 gate existed in the .cmd flavors;
- a quoted PYTHON override broke block parsing.

Text-level assertions run on every OS; behavioral assertions run natively on
Windows only.
"""

import os
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from bash_support import run_with_timeout, skip_if_prior_subprocess_timeout

REPO_ROOT = Path(__file__).resolve().parents[1]
CMD_LAUNCHERS = (
    REPO_ROOT / "xuunity_light_unity_mcp.cmd",
    REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.cmd",
    REPO_ROOT / "templates" / "run.cmd",
)
VERSION_PROBE = 'sys.version_info >= (3, 10)'


class CmdLauncherTextContractTest(unittest.TestCase):
    def test_no_parse_time_errorlevel_expansion(self):
        for launcher in CMD_LAUNCHERS:
            text = launcher.read_text(encoding="utf-8")
            self.assertNotIn(
                "%ERRORLEVEL%",
                text,
                f"{launcher.name}: use goto flow + `if errorlevel` / explicit exit codes; "
                "%ERRORLEVEL% inside parenthesized blocks expands at parse time",
            )

    def test_no_bare_exit_b(self):
        # A top-level batch that terminates via bare `exit /b` makes cmd.exe /c
        # exit 0 regardless of the prior ERRORLEVEL (caught live by the first
        # Windows e2e run: ensure-ready failed correctly but the wrapper
        # reported success). Use explicit codes, or end the script with the
        # delegated command so its ERRORLEVEL becomes the process exit code.
        for launcher in CMD_LAUNCHERS:
            text = launcher.read_text(encoding="utf-8")
            self.assertNotRegex(
                text,
                r"(?m)^\s*exit /b\s*$",
                f"{launcher.name}: bare `exit /b` swallows the exit code under cmd /c",
            )

    def test_python_invocation_ends_the_script(self):
        # The natural-end pattern is what propagates the delegated python exit
        # code through `cmd /c`; anything after the run line would reset it.
        for launcher in CMD_LAUNCHERS:
            text = launcher.read_text(encoding="utf-8").rstrip()
            last_line = text.splitlines()[-1]
            self.assertIn(
                "%XUUNITY_PYTHON_CMD%",
                last_line,
                f"{launcher.name}: the delegated python run must be the last executed line",
            )

    def test_interpreter_probe_gates_version_and_store_stub(self):
        for launcher in CMD_LAUNCHERS:
            text = launcher.read_text(encoding="utf-8")
            self.assertIn(VERSION_PROBE, text, launcher.name)

    def test_launchers_default_pythonutf8(self):
        for launcher in CMD_LAUNCHERS:
            text = launcher.read_text(encoding="utf-8")
            self.assertIn("PYTHONUTF8", text, launcher.name)

    def test_crlf_line_endings(self):
        for launcher in CMD_LAUNCHERS:
            data = launcher.read_bytes()
            self.assertNotIn(
                b"\r\r",
                data,
                f"{launcher.name}: double carriage returns",
            )
            lone_lf = data.replace(b"\r\n", b"").count(b"\n")
            self.assertEqual(
                lone_lf,
                0,
                f"{launcher.name}: batch files must be CRLF end to end",
            )


@unittest.skipUnless(os.name == "nt", "native Windows .cmd behavior")
class CmdLauncherWindowsBehaviorTest(unittest.TestCase):
    def setUp(self):
        skip_if_prior_subprocess_timeout(self)

    def run_wrapper(self, launcher: Path, args: list[str], env_overrides: dict[str, str]):
        env = dict(os.environ)
        env.update(env_overrides)
        return run_with_timeout(
            ["cmd.exe", "/d", "/c", str(launcher), *args],
            cwd=str(REPO_ROOT),
            env=env,
            timeout_seconds=120,
        )

    def test_broken_python_override_fails_with_nonzero_exit(self):
        for launcher in CMD_LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                completed = self.run_wrapper(
                    launcher,
                    ["--help"],
                    {"PYTHON": r"C:\definitely\missing\python.exe"},
                )
                self.assertNotEqual(completed.returncode, 0, completed.stdout)
                self.assertIn("not a working Python", completed.stderr)

    def test_quoted_python_override_is_tolerated(self):
        completed = self.run_wrapper(
            REPO_ROOT / "xuunity_light_unity_mcp.cmd",
            ["--help"],
            {"PYTHON": f'"{sys.executable}"'},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("usage:", completed.stdout.lower())

    def test_unquoted_python_override_with_spaces_still_works(self):
        completed = self.run_wrapper(
            REPO_ROOT / "xuunity_light_unity_mcp.cmd",
            ["--help"],
            {"PYTHON": sys.executable},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("usage:", completed.stdout.lower())

    def test_nonzero_python_exit_code_propagates_through_wrapper(self):
        completed = self.run_wrapper(
            REPO_ROOT / "xuunity_light_unity_mcp.cmd",
            ["definitely-not-a-command"],
            {"PYTHON": sys.executable},
        )
        self.assertNotEqual(
            completed.returncode,
            0,
            "python exited nonzero but cmd /c reported success: "
            f"stdout={completed.stdout[:300]} stderr={completed.stderr[:300]}",
        )
        self.assertIn("argv as received", completed.stderr)


if __name__ == "__main__":
    unittest.main()
