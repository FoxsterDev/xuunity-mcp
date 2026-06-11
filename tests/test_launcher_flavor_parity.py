"""Cross-flavor launcher parity: .sh, .cmd, and .ps1 must speak one contract.

On Windows all three wrapper flavors are executed and compared byte-for-byte
(after normalizing the flavor's own file name in help output). On POSIX the
.sh flavor is exercised as the baseline and the cmd/ps1 comparisons skip.

Phase 3 of XUUNITY_MCP_THIN_LAUNCHER_PYTHON_CORE_DESIGN_2026-06-11.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from bash_support import resolve_bash_executable, run_with_timeout, skip_if_prior_subprocess_timeout

REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_SH = REPO_ROOT / "xuunity_light_unity_mcp.sh"
WRAPPER_CMD = REPO_ROOT / "xuunity_light_unity_mcp.cmd"
WRAPPER_PS1 = REPO_ROOT / "xuunity_light_unity_mcp.ps1"
NAME_TOKEN = "<LAUNCHER>"


def resolve_powershell_executable() -> str:
    for candidate in ("pwsh", "powershell"):
        located = shutil.which(candidate)
        if located:
            return located
    return ""


class LauncherFlavorParityTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)

    def make_env(self) -> dict:
        env = dict(os.environ)
        env["PYTHON"] = sys.executable
        # Native path on purpose: a POSIX-looking value would be MSYS-converted
        # by the Git Bash flavor but passed through verbatim by cmd/powershell,
        # making the flavors diverge for test-fixture reasons only.
        env["XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR"] = os.path.join(
            tempfile.gettempdir(), "nonexistent-xuunity-neutral-dir"
        )
        for key in (
            "XUUNITY_LIGHT_UNITY_MCP_SOURCE_ROOT",
            "XUUNITY_LIGHT_UNITY_MCP_SERVER",
            "XUUNITY_LIGHT_UNITY_MCP_INSTALL_TARGET",
            "XUUNITY_LIGHT_UNITY_MCP_AIRROOT",
            "XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME",
        ):
            env.pop(key, None)
        return env

    def normalize(self, text: str) -> str:
        for name in (WRAPPER_SH.name, WRAPPER_CMD.name, WRAPPER_PS1.name):
            text = text.replace(name, NAME_TOKEN)
        return text.replace("\r\n", "\n")

    def run_flavor(self, flavor: str, args: list, env: dict):
        if flavor == "sh":
            cmd = [resolve_bash_executable(), WRAPPER_SH.as_posix(), *args]
        elif flavor == "cmd":
            cmd = ["cmd.exe", "/c", str(WRAPPER_CMD), *args]
        elif flavor == "ps1":
            powershell = resolve_powershell_executable()
            self.assertTrue(powershell, "no powershell/pwsh executable found")
            cmd = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(WRAPPER_PS1), *args]
        else:
            raise AssertionError(f"unknown flavor: {flavor}")
        completed = run_with_timeout(cmd, env=env, timeout_seconds=120)
        return completed.returncode, self.normalize(completed.stdout), self.normalize(completed.stderr)

    def available_flavors(self) -> list:
        if os.name == "nt":
            return ["sh", "cmd", "ps1"]
        return ["sh"]

    def assert_flavors_agree(self, args: list, env_factory) -> dict:
        results = {}
        for flavor in self.available_flavors():
            results[flavor] = self.run_flavor(flavor, args, env_factory())
        baseline = results["sh"]
        for flavor, result in results.items():
            self.assertEqual(baseline[0], result[0], f"exit code differs for {flavor}: {result[2]}")
            self.assertEqual(baseline[1], result[1], f"stdout differs for {flavor}")
        return results

    def test_help_contract_across_flavors(self) -> None:
        results = self.assert_flavors_agree(["--help"], self.make_env)
        self.assertEqual(0, results["sh"][0], results["sh"][2])
        self.assertIn(f"Usage: {NAME_TOKEN} [--compact-summary] <command> [args]", results["sh"][1])

    def test_mode_help_contract_across_flavors(self) -> None:
        results = self.assert_flavors_agree(["devmode", "--help"], self.make_env)
        self.assertEqual(0, results["sh"][0], results["sh"][2])
        self.assertIn("Switch a Unity project to local XUUnity Light Unity MCP package development.", results["sh"][1])

    def test_setup_plan_contract_across_flavors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = temp_root / "FakeProject"
            (project_root / "Assets").mkdir(parents=True)
            (project_root / "Packages").mkdir(parents=True)
            (project_root / "ProjectSettings").mkdir(parents=True)
            (project_root / "Packages" / "manifest.json").write_text(
                json.dumps({"dependencies": {}}, indent=2) + "\n", encoding="utf-8"
            )
            (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "m_EditorVersion: 2021.3.58f1\n", encoding="utf-8"
            )

            def env_factory() -> dict:
                env = self.make_env()
                env["CODEX_TOOLS_HOME"] = str(temp_root / "codex-tools")
                env["CLAUDE_TOOLS_HOME"] = str(temp_root / "claude-tools")
                return env

            results = self.assert_flavors_agree(
                ["setup-plan", "--project-root", str(project_root)], env_factory
            )
            self.assertEqual(0, results["sh"][0], results["sh"][2])
            plan = json.loads(results["sh"][1])
            self.assertEqual("setup_plan", plan["action"])


if __name__ == "__main__":
    unittest.main()
