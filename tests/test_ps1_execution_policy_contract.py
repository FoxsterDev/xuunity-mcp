"""Windows .ps1 launcher contract under stock ExecutionPolicy.

Stock Windows PowerShell 5.1 defaults to ExecutionPolicy=Restricted, which
refuses to run any .ps1 file — the 2026-06-17 retro class 8 setup wall. The
parity suite always passes -ExecutionPolicy Bypass, so it can never see that
wall. This file pins the real contract:

- text level (every OS): both .ps1 wrappers carry in-file guidance naming the
  .cmd fallback and the Bypass invocation, and stay CRLF end to end;
- behavior level (native Windows): under Restricted policy the wrapper fails
  loudly (non-zero exit, no usage output) instead of silently succeeding, and
  the documented Bypass invocation works on the same host.
"""

import os
import shutil
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from bash_support import run_with_timeout, skip_if_prior_subprocess_timeout

REPO_ROOT = Path(__file__).resolve().parents[1]
PS1_LAUNCHERS = (
    REPO_ROOT / "xuunity_light_unity_mcp.ps1",
    REPO_ROOT / "templates" / "run.ps1",
)
GUIDANCE_MARKER = "-ExecutionPolicy Bypass -File"


def installed_powershell_hosts() -> list:
    hosts = []
    for candidate in ("powershell", "pwsh"):
        located = shutil.which(candidate)
        if located:
            hosts.append(located)
    return hosts


class Ps1ExecutionPolicyTextContractTest(unittest.TestCase):
    def test_wrappers_carry_execution_policy_guidance(self) -> None:
        for launcher in PS1_LAUNCHERS:
            text = launcher.read_text(encoding="utf-8")
            self.assertIn("ExecutionPolicy=Restricted", text, launcher.name)
            self.assertIn(GUIDANCE_MARKER, text, launcher.name)
            self.assertIn(".cmd", text, launcher.name)

    def test_crlf_line_endings(self) -> None:
        for launcher in PS1_LAUNCHERS:
            data = launcher.read_bytes()
            self.assertNotIn(b"\r\r", data, f"{launcher.name}: double carriage returns")
            lone_lf = data.replace(b"\r\n", b"").count(b"\n")
            self.assertEqual(
                lone_lf,
                0,
                f"{launcher.name}: PowerShell wrappers must stay CRLF end to end",
            )


@unittest.skipUnless(os.name == "nt", "ExecutionPolicy only exists on Windows hosts")
class Ps1ExecutionPolicyWindowsBehaviorTest(unittest.TestCase):
    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)
        self.hosts = installed_powershell_hosts()
        if not self.hosts:
            self.skipTest("no powershell/pwsh executable found")

    def make_env(self) -> dict:
        env = dict(os.environ)
        env["PYTHON"] = sys.executable
        env["PYTHONUTF8"] = "1"
        return env

    def run_wrapper(self, host: str, policy: str, launcher: Path):
        return run_with_timeout(
            [
                host,
                "-NoProfile",
                "-ExecutionPolicy",
                policy,
                "-File",
                str(launcher),
                "--help",
            ],
            cwd=str(REPO_ROOT),
            env=self.make_env(),
            timeout_seconds=120,
        )

    def test_restricted_policy_fails_loudly_not_silently(self) -> None:
        launcher = REPO_ROOT / "xuunity_light_unity_mcp.ps1"
        for host in self.hosts:
            with self.subTest(host=Path(host).name):
                completed = self.run_wrapper(host, "Restricted", launcher)
                self.assertNotEqual(
                    0,
                    completed.returncode,
                    "Restricted policy must refuse the script with a non-zero exit; "
                    f"stdout: {completed.stdout[:400]}",
                )
                self.assertNotIn("usage", completed.stdout.lower())

    def test_documented_bypass_invocation_works(self) -> None:
        launcher = REPO_ROOT / "xuunity_light_unity_mcp.ps1"
        for host in self.hosts:
            with self.subTest(host=Path(host).name):
                completed = self.run_wrapper(host, "Bypass", launcher)
                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertIn("usage", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
