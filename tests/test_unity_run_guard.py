"""Host-wide Unity slot lock, owned-process cleanup, and the matrix script's stop path."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_TESTING_DIR = REPO_ROOT / "scripts" / "testing"
for entry in (SCRIPTS_TESTING_DIR, REPO_ROOT / "templates", Path(__file__).resolve().parent):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import unity_run_guard as guard
from bash_support import resolve_bash_executable, skip_if_prior_subprocess_timeout

MATRIX_SCRIPT = SCRIPTS_TESTING_DIR / "run_unity_version_matrix.sh"
ROLLOUT_SCRIPT = SCRIPTS_TESTING_DIR / "run_consumer_rollout.py"
FAKE_VERSION = "9999.0.0f1"


class UnitySlotLockTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.lock = Path(temp.name) / "state" / "unity_slot.lock.json"
        self.alive: set[int] = {100, 200}
        self.started = {100: 1000.0, 200: 2000.0}

    def acquire(self, pid: int, owner: str = "matrix") -> dict:
        return guard.acquire_slot(
            self.lock, pid=pid, owner=owner, command=f"run --pid {pid}",
            pid_is_alive=lambda value: value in self.alive,
            process_start_time=lambda value: self.started.get(value),
        )

    def test_acquire_records_the_holder_and_release_frees_the_slot(self) -> None:
        result = self.acquire(100)
        self.assertTrue(result["acquired"])
        holder = json.loads(self.lock.read_text(encoding="utf-8"))
        self.assertEqual((100, "matrix", "run --pid 100"), (holder["pid"], holder["owner"], holder["command"]))
        self.assertRegex(holder["started_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(1000.0, holder["process_started_epoch"])
        self.assertEqual({"released": False, "reason": "held_by_another_pid", "holder": holder},
                         guard.release_slot(self.lock, pid=200))
        self.assertTrue(guard.release_slot(self.lock, pid=100)["released"])
        self.assertFalse(self.lock.exists())
        self.assertEqual("no_lock", guard.release_slot(self.lock, pid=100)["reason"])

    def test_a_second_run_is_refused_with_the_holders_details(self) -> None:
        self.acquire(100, owner="rollout")
        with self.assertRaises(guard.UnitySlotBusy) as caught:
            self.acquire(200)
        self.assertEqual(100, caught.exception.holder["pid"])
        self.assertEqual("rollout", caught.exception.holder["owner"])
        self.assertEqual("run --pid 100", caught.exception.holder["command"])
        self.assertTrue(self.acquire(100)["reentrant"])

    def test_a_stale_lock_is_taken_over_and_says_why(self) -> None:
        self.acquire(100)
        self.alive.discard(100)
        self.assertEqual("holder_exited", self.acquire(200)["stale_lock_taken_over"])
        self.assertEqual(200, json.loads(self.lock.read_text(encoding="utf-8"))["pid"])

    def test_a_reused_holder_pid_is_stale(self) -> None:
        self.acquire(100)
        self.started[100] = 5000.0
        self.assertEqual("holder_pid_reused", self.acquire(200)["stale_lock_taken_over"])

    def test_an_unreadable_lock_is_stale(self) -> None:
        self.lock.parent.mkdir(parents=True)
        self.lock.write_text("{", encoding="utf-8")
        self.assertEqual("unreadable", self.acquire(200)["stale_lock_taken_over"])

    def test_the_default_path_sits_in_the_neutral_install_state_dir_and_honours_the_override(self) -> None:
        with mock.patch.dict(os.environ, {"XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR": "/x/neutral"}, clear=False):
            os.environ.pop(guard.LOCK_FILE_ENV, None)
            self.assertEqual(Path("/x/neutral") / "state" / "unity_slot.lock.json", guard.default_lock_path())
        with mock.patch.dict(os.environ, {guard.LOCK_FILE_ENV: "/y/slot.json"}, clear=False):
            self.assertEqual(Path("/y/slot.json"), guard.default_lock_path())

    def test_cli_refuses_with_exit_code_and_holder_json(self) -> None:
        self.acquire(100)
        with mock.patch.object(guard, "_adapter_callbacks", return_value=(lambda pid: pid in self.alive, self.started.get)), \
                mock.patch("builtins.print") as printed:
            code = guard.main(["lock-acquire", "--lock-file", str(self.lock), "--owner", "second", "--pid", "200"])
        self.assertEqual(guard.EXIT_SLOT_BUSY, code)
        payload = json.loads(printed.call_args.args[0])
        self.assertEqual(("unity_slot_busy", 100), (payload["error"], payload["holder"]["pid"]))


class OwnedRunProcessTests(unittest.TestCase):
    RUN = Path("/tmp/matrix/20261120T000000Z/projects")
    UNITY = "/Applications/Unity/Hub/Editor/6000.0.1f1/Unity.app/Contents/MacOS/Unity"

    def owned(self, processes: list[dict], tracked: list[dict] | None = None, started: dict | None = None) -> dict:
        rows = guard.owned_run_processes(
            processes, projects_root=self.RUN, tracked=tracked or [],
            process_start_time=lambda pid: (started or {}).get(pid), exclude_pids={1, 999},
        )
        return {row["pid"]: row["reason"] for row in rows}

    def test_only_this_runs_unity_processes_and_their_descendants_are_owned(self) -> None:
        processes = [
            {"pid": 10, "ppid": 1, "command": f"{self.UNITY} -batchmode -projectPath {self.RUN}/SampleProject_6000_0_1f1"},
            {"pid": 11, "ppid": 10, "command": "/Applications/Unity/Hub/Editor/6000.0.1f1/Unity.app/Contents/Resources/PackageManager/Server/UnityPackageManager"},
            {"pid": 12, "ppid": 11, "command": "node helper"},
            {"pid": 13, "ppid": 10, "command": "/Applications/Unity/Hub/Editor/6000.0.1f1/Unity.app/Contents/Frameworks/UnityLicensingClient.app/Contents/MacOS/Unity.Licensing.Client"},
            {"pid": 20, "ppid": 1, "command": f"{self.UNITY} -projectPath /Users/someone/Projects/OtherGame"},
            {"pid": 21, "ppid": 20, "command": "UnityPackageManager"},
            {"pid": 30, "ppid": 1, "command": f"/bin/zsh -c echo {self.RUN}/SampleProject"},
            {"pid": 999, "ppid": 10, "command": "python3 unity_run_guard.py stop-run"},
        ]
        self.assertEqual(
            {10: "unity_main_editor_for_run_project", 11: "descendant_of_owned_process", 12: "descendant_of_owned_process"},
            self.owned(processes),
        )

    def test_a_similarly_named_run_directory_is_not_this_run(self) -> None:
        processes = [{"pid": 10, "ppid": 1, "command": f"{self.UNITY} -projectPath {self.RUN}-other/SampleProject"}]
        self.assertEqual({}, self.owned(processes))

    def test_a_tracked_child_needs_its_recorded_start_time(self) -> None:
        processes = [
            {"pid": 40, "ppid": 5, "command": "bash xuunity_light_unity_mcp.sh ensure-ready"},
            {"pid": 41, "ppid": 40, "command": "python3 server.py ensure-ready"},
            {"pid": 50, "ppid": 5, "command": "unrelated reuse of a recorded pid"},
            {"pid": 60, "ppid": 5, "command": "tracked without a start time"},
        ]
        tracked = [
            {"pid": 40, "process_started_epoch": 100.0},
            {"pid": 50, "process_started_epoch": 100.0},
            {"pid": 60, "process_started_epoch": None},
            {"pid": 70, "process_started_epoch": 100.0},
        ]
        started = {40: 101.0, 50: 9000.0, 60: 100.0}
        self.assertEqual({40: "tracked_child", 41: "descendant_of_owned_process"}, self.owned(processes, tracked, started))

    def test_stop_run_terminates_owned_processes_and_reports_survivors(self) -> None:
        alive = {10, 11}
        reports = [
            {"available": True, "processes": [
                {"pid": 10, "ppid": 1, "command": f"{self.UNITY} -projectPath {self.RUN}/P"},
                {"pid": 11, "ppid": 10, "command": "UnityPackageManager"},
            ]},
            {"available": True, "processes": [{"pid": 11, "ppid": 1, "command": "UnityPackageManager"}]},
        ]
        terminated: list[int] = []

        def terminate(pid: int, _timeout_ms: int) -> bool:
            terminated.append(pid)
            alive.discard(pid)
            return True

        result = guard.stop_run(
            self.RUN, process_report_fn=lambda: reports.pop(0) if reports else {"available": True, "processes": []},
            terminate_fn=terminate, pid_is_alive=lambda pid: pid in alive, process_start_time=lambda pid: None,
        )
        self.assertEqual("stopped", result["status"])
        self.assertEqual([11, 10], terminated)
        self.assertEqual([], result["survivors"])

        blind = guard.stop_run(self.RUN, process_report_fn=lambda: {"available": False}, terminate_fn=terminate)
        self.assertEqual("process_visibility_unavailable", blind["status"])
        self.assertEqual([], blind["terminated"])


@unittest.skipIf(os.name == "nt", "the fake editor is a POSIX script; Windows covers the guard through its unit tests")
class MatrixStopPathTests(unittest.TestCase):
    def setUp(self) -> None:
        skip_if_prior_subprocess_timeout(self)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.pid_file = self.root / "fake_unity.pid"
        if sys.platform == "darwin":
            fake = self.root / "editors" / FAKE_VERSION / "Unity.app" / "Contents" / "MacOS" / "Unity"
        else:
            fake = self.root / "editors" / FAKE_VERSION / "Editor" / "Unity"
        fake.parent.mkdir(parents=True)
        fake.write_text(f'#!/bin/sh\necho $$ > "{self.pid_file}"\nexec sleep 300\n', encoding="utf-8")
        fake.chmod(0o755)
        self.env = dict(os.environ)
        self.env.update({
            "XUUNITY_UNITY_EDITOR_ROOTS": str(self.root / "editors"),
            guard.LOCK_FILE_ENV: str(self.root / "slot" / "unity_slot.lock.json"),
            "TMPDIR": str(self.root),
        })
        self.command = [
            resolve_bash_executable(), str(MATRIX_SCRIPT), "--artifact-root", str(self.root / "artifacts"),
            "--skip-package-self-tests", FAKE_VERSION,
        ]

    def start(self) -> subprocess.Popen:
        process = subprocess.Popen(
            self.command, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", start_new_session=True,
        )
        self.addCleanup(self.kill_group, process)
        return process

    @staticmethod
    def kill_group(process: subprocess.Popen) -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.communicate(timeout=10)
        except (subprocess.TimeoutExpired, ValueError):
            pass

    def wait_for(self, predicate, seconds: float = 60.0) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.1)
        return False

    @staticmethod
    def alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def test_term_ends_the_started_editor_records_stopped_and_releases_the_slot(self) -> None:
        process = self.start()
        self.assertTrue(self.wait_for(self.pid_file.is_file), "the matrix never started the fake editor")
        self.assertTrue(self.wait_for(lambda: self.pid_file.read_text().strip().isdigit(), 5))
        fake_pid = int(self.pid_file.read_text().strip())
        lock_path = Path(self.env[guard.LOCK_FILE_ENV])
        self.assertEqual(process.pid, json.loads(lock_path.read_text(encoding="utf-8"))["pid"])
        self.assertTrue(self.alive(fake_pid))

        os.kill(process.pid, signal.SIGTERM)
        try:
            _stdout, stderr = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            self.fail("the matrix did not exit after TERM")

        self.assertEqual(143, process.returncode, stderr[-600:])
        self.assertTrue(self.wait_for(lambda: not self.alive(fake_pid), 10), "the fake editor survived the stop")
        self.assertFalse(lock_path.exists(), "the Unity slot was not released")
        run_root = next((self.root / "artifacts").iterdir())
        summary = (run_root / "summary.tsv").read_text(encoding="utf-8").splitlines()
        self.assertEqual([FAKE_VERSION, "stopped", "interrupted"], summary[-1].split("\t")[:3])
        result = json.loads((run_root / "results" / FAKE_VERSION / "result.json").read_text(encoding="utf-8"))
        self.assertEqual("stopped", result["status"])
        cleanup = json.loads((run_root / "stop_cleanup.json").read_text(encoding="utf-8"))
        self.assertEqual("stopped", cleanup["status"])
        self.assertIn(fake_pid, [item["pid"] for item in cleanup["terminated"]])

    def test_a_held_slot_refuses_before_any_editor_starts(self) -> None:
        lock_path = Path(self.env[guard.LOCK_FILE_ENV])
        guard.acquire_slot(lock_path, pid=os.getpid(), owner="another-session", command="pytest holder")
        self.addCleanup(lambda: lock_path.unlink() if lock_path.exists() else None)
        process = self.start()
        try:
            _stdout, stderr = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            self.fail("the matrix did not refuse a held slot")
        self.assertEqual(1, process.returncode)
        self.assertIn("unity_slot_busy", stderr)
        self.assertIn("another-session", stderr)
        self.assertFalse(self.pid_file.exists(), "an editor was started while the slot was held")
        self.assertEqual(os.getpid(), json.loads(lock_path.read_text(encoding="utf-8"))["pid"])


class RunnerWiringTests(unittest.TestCase):
    def test_the_matrix_takes_the_slot_before_the_first_entry_and_tracks_every_step(self) -> None:
        text = MATRIX_SCRIPT.read_text(encoding="utf-8")
        self.assertLess(text.index("\nacquire_unity_slot\n"), text.index('for unity_version in "${VERSIONS[@]}"; do'))
        self.assertLess(text.index('UNITY_SLOT_LOCK_FILE="$(python3 "$RUN_GUARD" lock-path)"'),
                        text.index('export XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR='))
        for trapped in ("INT", "TERM", "HUP", "EXIT"):
            self.assertRegex(text, rf"trap [^\n]+ {trapped}\n")
        self.assertIn('if run_tracked "$@" >"$stdout_path" 2>"$stderr_path"; then', text)
        self.assertIn('run_tracked "$unity_path" \\\n    -batchmode', text)

    def test_the_rollout_helper_takes_the_slot_for_execute(self) -> None:
        text = ROLLOUT_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("acquire_slot(", text)
        self.assertIn("release_slot(", text)
        self.assertIn("unity_slot_busy", text)


if __name__ == "__main__":
    unittest.main()
