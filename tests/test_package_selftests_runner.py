"""The batch self-test runner prepares the project, bounds the run, and never leaves its editor behind."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_TESTING_DIR = REPO_ROOT / "scripts" / "testing"
for entry in (SCRIPTS_TESTING_DIR, REPO_ROOT / "templates", Path(__file__).resolve().parent):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import unity_run_guard as guard
from bash_support import resolve_bash_executable, run_with_timeout, skip_if_prior_subprocess_timeout

RUNNER = SCRIPTS_TESTING_DIR / "run_package_selftests.sh"
PASSING_RESULTS = '<test-run result="Passed" total="3" passed="3" failed="0" skipped="0" inconclusive="0"/>'
FAILING_RESULTS = '<test-run result="Failed(Child)" total="3" passed="2" failed="1" skipped="0" inconclusive="0"/>'
EMPTY_RESULTS = '<test-run result="Passed" total="0" passed="0" failed="0" skipped="0" inconclusive="0"/>'


@unittest.skipIf(os.name == "nt", "the fake editor is a POSIX script")
class PackageSelftestsRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.project = self.root / "Project"
        (self.project / "Packages").mkdir(parents=True)
        (self.project / "ProjectSettings").mkdir()
        (self.project / "ProjectSettings" / "ProjectVersion.txt").write_text(
            "m_EditorVersion: 6000.5.0f1\n", encoding="utf-8"
        )
        self.write_manifest({"com.xuunity.light-mcp": "file:../pkg"})
        self.args_file = self.root / "unity_args.txt"
        self.pid_file = self.root / "unity.pid"
        self.env = dict(os.environ)
        self.env[guard.LOCK_FILE_ENV] = str(self.root / "slot" / "unity_slot.lock.json")
        self.env["XUUNITY_LIGHT_UNITY_MCP_PYTHON"] = Path(sys.executable).as_posix()

    def write_manifest(self, dependencies: dict) -> None:
        (self.project / "Packages" / "manifest.json").write_text(
            json.dumps({"dependencies": dependencies}), encoding="utf-8"
        )

    def fake_unity(self, body: str) -> Path:
        unity = self.root / "Unity"
        unity.write_text(
            "#!/bin/sh\n"
            f'echo "$@" > "{self.args_file}"\n'
            f'echo $$ > "{self.pid_file}"\n'
            'results=""; log=""\n'
            'while [ $# -gt 0 ]; do\n'
            '  case "$1" in -testResults) results="$2";; -logFile) log="$2";; esac\n'
            "  shift\n"
            "done\n"
            'echo "fake editor log line" > "$log"\n' + body,
            encoding="utf-8",
        )
        unity.chmod(0o755)
        return unity

    def run_runner(self, unity: Path, *extra: str, timeout_seconds: int = 120) -> tuple[int, dict]:
        completed = run_with_timeout(
            [resolve_bash_executable(), str(RUNNER), str(unity), str(self.project), *extra],
            env=self.env, timeout_seconds=timeout_seconds,
        )
        return completed.returncode, json.loads(completed.stdout)

    def test_prepares_the_project_runs_with_its_own_log_and_passes(self) -> None:
        unity = self.fake_unity(f"printf '%s' '{PASSING_RESULTS}' > \"$results\"\n")
        code, payload = self.run_runner(unity, "--filter", "JournalTruth")

        self.assertEqual(0, code, payload)
        self.assertEqual("passed", payload["status"])
        self.assertEqual(3, payload["results"]["total"])
        self.assertTrue(payload["testables_entry_added"])
        manifest = json.loads((self.project / "Packages" / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("com.unity.test-framework", manifest["dependencies"])
        self.assertEqual(["com.xuunity.light-mcp"], manifest["testables"])
        arguments = self.args_file.read_text(encoding="utf-8")
        for expected in ("-batchmode", "-runTests", "-testPlatform EditMode", "-testFilter JournalTruth", "-logFile "):
            self.assertIn(expected, arguments)
        self.assertNotIn("-quit", arguments)
        self.assertTrue(Path(payload["log_path"]).is_file())
        self.assertFalse(Path(self.env[guard.LOCK_FILE_ENV]).exists(), "the Unity slot was not released")

        code, again = self.run_runner(unity)
        self.assertEqual(0, code)
        self.assertFalse(again["testables_entry_added"])

    def test_failed_and_empty_runs_fail(self) -> None:
        for results, error in ((FAILING_RESULTS, "tests_failed"), (EMPTY_RESULTS, "no_tests_matched")):
            with self.subTest(error=error):
                unity = self.fake_unity(f"printf '%s' '{results}' > \"$results\"\n")
                code, payload = self.run_runner(unity)
                self.assertEqual(1, code)
                self.assertEqual(("failed", error), (payload["status"], payload["error"]))

    def test_an_editor_that_never_writes_results_is_stopped_at_the_bound(self) -> None:
        unity = self.fake_unity("exec sleep 300\n")
        code, payload = self.run_runner(unity, "--bound-seconds", "3")

        self.assertEqual(1, code)
        self.assertEqual("results_not_written_within_bound", payload["error"])
        self.assertTrue(payload["editor_stopped_by_runner"])
        self.assertEqual(["fake editor log line"], payload["log_tail"])
        pid = int(self.pid_file.read_text().strip())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertFalse(Path(self.env[guard.LOCK_FILE_ENV]).exists())

    def test_an_editor_that_exits_without_results_fails_at_once(self) -> None:
        code, payload = self.run_runner(self.fake_unity("exit 0\n"), "--bound-seconds", "60")
        self.assertEqual(1, code)
        self.assertEqual("results_not_written", payload["error"])
        self.assertFalse(payload["editor_stopped_by_runner"])
        self.assertLess(payload["elapsed_seconds"], 30)

    def test_refusals_start_no_editor(self) -> None:
        unity = self.fake_unity("exit 0\n")
        lock_path = Path(self.env[guard.LOCK_FILE_ENV])
        guard.acquire_slot(lock_path, pid=os.getpid(), owner="another-session", command="holder")
        code, busy = self.run_runner(unity)
        self.assertEqual(3, code)
        self.assertEqual(("unity_slot_busy", "another-session"), (busy["error"], busy["holder"]["owner"]))
        untouched = json.loads((self.project / "Packages" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual({"dependencies": {"com.xuunity.light-mcp": "file:../pkg"}}, untouched)
        lock_path.unlink()

        self.write_manifest({"com.unity.ugui": "2.0.0"})
        code, undeclared = self.run_runner(unity)
        self.assertEqual(2, code)
        self.assertEqual("package_not_declared", undeclared["error"])
        self.assertFalse(lock_path.exists(), "a refused run kept the Unity slot")

        code, missing = self.run_runner(self.root / "NoSuchUnity")
        self.assertEqual(2, code)
        self.assertEqual("unity_executable_not_found", missing["error"])
        self.assertFalse(self.pid_file.exists())


if __name__ == "__main__":
    unittest.main()
