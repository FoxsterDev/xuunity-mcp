"""README Windows quickstart, executed verbatim under Windows PowerShell 5.1.

The README tells colleagues to run the ``.cmd`` launcher from PowerShell with
a ``>`` redirect for the plan file. Two host behaviors make that sequence a
real compatibility claim, and neither was ever executed in CI:

- stock PowerShell 5.1 redirects native output as UTF-16LE with a BOM
  (retro class: "Plan-file UTF-16 rejection"), so ``setup-apply`` must accept
  a UTF-16 plan file;
- the ``.cmd`` flavor must be immune to the default ExecutionPolicy, so the
  session runs WITHOUT ``-ExecutionPolicy Bypass``.

The test drives setup-plan > plan → setup-apply --plan-file → validate-setup
through ``xuunity_light_unity_mcp.cmd`` on a spaces+Cyrillic project path and
asserts the plan file really was UTF-16 (proving the class was simulated, not
dodged).
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

from bash_support import run_with_timeout, skip_if_prior_subprocess_timeout
from test_mcp_stdio_e2e import make_launcher_env, scaffold_unity_project

REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "verbatim Windows PowerShell 5.1 quickstart")
class ReadmePowerShell51QuickstartTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)
        self.powershell = shutil.which("powershell")
        if not self.powershell:
            self.skipTest("Windows PowerShell 5.1 (powershell.exe) not found on this host")

    def test_setup_plan_apply_validate_through_cmd_wrapper_from_powershell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            project_root = scaffold_unity_project(
                temp_root / "Юнити Проекты" / "Проект 5.1"
            )
            plan_dir = temp_root / "Планы PS"
            plan_dir.mkdir()
            plan_path = plan_dir / "xuunity-setup-plan.json"
            env = make_launcher_env(temp_root / "neutral-install")

            script = (
                '$ErrorActionPreference = "Stop"\n'
                f'Set-Location -LiteralPath "{REPO_ROOT}"\n'
                f'.\\xuunity_light_unity_mcp.cmd setup-plan --project-root "{project_root}" > "{plan_path}"\n'
                "if ($LASTEXITCODE -ne 0) { exit 11 }\n"
                f'.\\xuunity_light_unity_mcp.cmd setup-apply --plan-file "{plan_path}" --project-root "{project_root}" --yes\n'
                "if ($LASTEXITCODE -ne 0) { exit 12 }\n"
                f'.\\xuunity_light_unity_mcp.cmd validate-setup --project-root "{project_root}"\n'
                "if ($LASTEXITCODE -ne 0) { exit 13 }\n"
            )

            completed = run_with_timeout(
                [self.powershell, "-NoProfile", "-Command", script],
                cwd=str(REPO_ROOT),
                env=env,
                timeout_seconds=300,
            )

            self.assertEqual(
                0,
                completed.returncode,
                "quickstart step failed (11=plan 12=apply 13=validate): "
                f"stdout={completed.stdout[-2000:]} stderr={completed.stderr[-2000:]}",
            )

            plan_bytes = plan_path.read_bytes()
            self.assertTrue(
                plan_bytes.startswith(b"\xff\xfe"),
                "PowerShell 5.1 `>` must have produced a UTF-16LE BOM plan file; "
                f"got leading bytes {plan_bytes[:4]!r} — the UTF-16 class was not exercised",
            )
            plan_text = plan_bytes.decode("utf-16")
            plan = json.loads(plan_text)
            self.assertEqual("setup_plan", plan.get("action"), plan_text[:400])

            manifest = json.loads(
                (project_root / "Packages" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertIn(
                "com.xuunity.light-mcp",
                manifest.get("dependencies", {}),
                "setup-apply must register the package in the project manifest",
            )


if __name__ == "__main__":
    unittest.main()
