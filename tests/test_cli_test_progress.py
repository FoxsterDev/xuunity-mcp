import sys
import tempfile
import time
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_cli_test_progress as progress
from server_core import write_json


def _utc(offset_seconds: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset_seconds))


class CliTestProgressTests(unittest.TestCase):
    def _read(self, data: dict | None, *, alive: bool) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            if data is not None:
                path = progress.cli_test_progress_path(root)
                path.parent.mkdir(parents=True, exist_ok=True)
                write_json(path, data)
            return progress.read_cli_test_progress(root, pid_is_alive=lambda _pid: alive)

    def _sidecar(self, **overrides) -> dict:
        data = {
            "schema": progress.CLI_TEST_PROGRESS_SCHEMA,
            "process_id": 777,
            "test_platform": "PlayMode",
            "run_phase": "running",
            "total": 230,
            "finished": 41,
            "passed": 40,
            "failed": 1,
            "last_started_test": "Tour.Capture_every_screen_and_state",
            "last_progress_at_utc": _utc(-5),
        }
        data.update(overrides)
        return data

    def test_absent_sidecar_adds_nothing(self) -> None:
        self.assertEqual({}, self._read(None, alive=True))

    UNITY = "/Applications/Unity/Hub/Editor/6000.5.0f1/Unity.app/Contents/MacOS/Unity"

    def _project(self, tmp: str, *, manifest: dict | None, lock: dict | None = None) -> Path:
        root = Path(tmp).resolve() / "Project"
        (root / "Packages").mkdir(parents=True)
        if manifest is not None:
            write_json(root / "Packages" / "manifest.json", {"dependencies": manifest})
        if lock is not None:
            write_json(root / "Packages" / "packages-lock.json", {"dependencies": lock})
        return root

    def _missing(self, root: Path, commands: list[tuple[int, str]], alive: bool = True) -> dict:
        return progress.read_cli_test_progress(
            root, pid_is_alive=lambda _pid: alive, process_commands=lambda: commands
        )

    def test_run_tests_without_the_test_framework_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, manifest={"com.unity.ugui": "2.0.0"}, lock={"com.unity.ugui": {"version": "2.0.0"}})
            commands = [
                (4242, f"{self.UNITY} -batchmode -projectPath {root} -runTests -testPlatform EditMode"),
                (4343, f"{self.UNITY} -batchmode -projectPath {root}Other -runTests"),
                (4444, f"{self.UNITY} -projectPath {root}"),
            ]
            view = self._missing(root, commands)
            self.assertEqual("test_framework_missing", view["status"])
            self.assertEqual([4242], view["process_ids"])
            self.assertEqual("unity_package_install_test_framework", view["recommended_recovery_tool"])
            self.assertIn("com.unity.test-framework", view["summary"])
            self.assertEqual({}, self._missing(root, commands, alive=False))
            self.assertEqual({}, self._missing(root, commands[1:]))

    def test_a_declared_or_resolved_test_framework_is_never_reported_missing(self) -> None:
        for manifest, lock in (
            ({"com.unity.test-framework": "1.4.5"}, None),
            ({"com.example.pkg": "1.0.0"}, {"com.unity.test-framework": {"version": "1.4.5"}}),
            (None, None),
        ):
            with self.subTest(manifest=manifest, lock=lock), tempfile.TemporaryDirectory() as tmp:
                root = self._project(tmp, manifest=manifest, lock=lock)
                commands = [(4242, f"{self.UNITY} -batchmode -projectPath {root} -runTests")]
                self.assertEqual({}, self._missing(root, commands))

    def test_a_failing_process_listing_adds_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, manifest={})

            def broken() -> list:
                raise OSError("ps unavailable")

            self.assertEqual({}, progress.read_cli_test_progress(root, pid_is_alive=lambda _pid: True, process_commands=broken))

    def test_live_run_reports_counts_and_the_test_in_flight(self) -> None:
        view = self._read(self._sidecar(), alive=True)
        self.assertEqual("running", view["status"])
        self.assertEqual(41, view["finished"])
        self.assertEqual("Tour.Capture_every_screen_and_state", view["last_started_test"])

    def test_quiet_live_run_is_flagged(self) -> None:
        view = self._read(self._sidecar(last_progress_at_utc=_utc(-900)), alive=True)
        self.assertEqual("running_without_progress", view["status"])

    def test_dead_process_mid_run_is_flagged(self) -> None:
        view = self._read(self._sidecar(), alive=False)
        self.assertEqual("process_exited_before_completion", view["status"])

    def test_completed_run_keeps_its_phase(self) -> None:
        view = self._read(self._sidecar(run_phase="completed", result_status="passed"), alive=False)
        self.assertEqual("completed", view["status"])
        self.assertEqual("passed", view["result_status"])

    def test_foreign_schema_is_ignored(self) -> None:
        self.assertEqual({}, self._read({"schema": "other"}, alive=True))


if __name__ == "__main__":
    unittest.main()
