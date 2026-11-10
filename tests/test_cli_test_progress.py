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
